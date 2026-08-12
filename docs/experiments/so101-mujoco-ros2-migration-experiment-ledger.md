---
task_id: so101-mujoco-ros2-migration
goal: Replace the Gazebo Python demonstration with an independently packaged MuJoCo ROS 2 demonstration.
success_contract: The MuJoCo implementation satisfies its ROS 2 and physical outcome contracts without changing or depending on the protected Gazebo Python tree.
main_base_commit: 8d85205286d2635d4ddbc91431c933dafb4eb661
task_base_commit: 2f5ebda79f72b452329326a8fbf02057f75f9049
behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
rejected_backup_commit: 3add34f8390b78a1f4a13ff49aefb2dc87638245
rejected_backup_branch: codex/so101-mujoco-ros2-pre-isolation-20260810
branch: codex/so101-mujoco-ros2-teleop
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
base_commit: 8d85205286d2635d4ddbc91431c933dafb4eb661
current_commit: a925a6f6fa09f0059a395a61509becda20606d34
last_verified_implementation_commit: a925a6f6fa09f0059a395a61509becda20606d34
ledger_commit_pending: true
task_status: TASK_14_TELEOP_INTEGRATION_PENDING_COMMIT
evidence_root: /tmp/so101-debug-mujoco-migration/
protected_nontracked_baseline_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
strict_physics_contract: The successful positive path must use physical contact and grasp forces with no weld, no equality constraint, no adhesion or adhesive actuator, no mocap body, no teleport or set-pose, no direct object qpos writes, and no direct object qvel writes.
confirmed_conclusions:
  - The rebased migration starts from the exact main baseline; CP-001.
  - EXP-036 is a VALID Task 12 dry-run behavioral failure at MoveIt time parameterization because joint acceleration limits are absent; CP-050.
  - User direction resumed Task 12 and authorized restoring the exact frozen joint-limit contract from the sole behavior source; CP-051.
  - EXP-037 is a VALID full-launch readiness failure because the diagnostic sampled controller states before the concurrently spawned gripper controller became active; CP-052.
  - User direction resumed Task 12 and authorized a bounded readiness-only correction under the existing overall deadline; CP-053.
  - EXP-038 is a VALID full-launch dry_run success, while EXP-039 is a VALID execute failure at MoveIt start-state validation; CP-055.
  - EXP-039 lacks the boundary-correlated trajectory first point and pre-execute joint sample required to distinguish request-time deviation from post-plan drift; CP-056.
  - EXP-040 validly confirms the trajectory first point exactly matched the request sample and joint drift accumulated during planning, before plan response; CP-057.
  - Installed controller-state provenance exposes reference, feedback, error, and output fields needed to determine whether the active position controller holds a command while physics drifts; CP-058.
  - EXP-041 validly shows constant current reference/output with changing feedback/error: desired does not change and the position command interface is present; CP-059.
  - EXP-044 validly shows freeze-plan-resume is nondeterministic: planning stays stationary while paused, but immediate resume can exceed the unchanged start tolerance before MoveIt validation; CP-063.
  - EXP-045 validly finds no preregistered 0.20-second stable window under the fixed controller reference within the unchanged 30-second deadline, so bounded settle-and-replan is not authorized for implementation; CP-064.
  - EXP-046 validly finds the unchanged stable-window predicate under the exact reviewed SO-101 dynamics, permitting the single separately preregistered safe-execute validation; CP-065.
  - EXP-047 validly proves the unchanged safe trajectory plans, executes through MoveIt and arm_controller, converges all six independent joint samples, and advances atomic MuJoCo evidence under the reviewed dynamics; CP-066.
  - EXP-075 qualifies the fail-closed transactional ResetWorld implementation, including two same-stack resets and fresh CUA evidence; CP-110.
  - EXP-076 validly restores the standard fork stack to CLOSE_READY with the formal Planning Scene, unpaused physics, zero fingertip contact, and negligible cup motion; CP-111.
  - EXP-081 validly proves a constraint-free physical micro-lift: the cup rises 2.097 mm, clears table support, and retains bilateral fingertip contact under the stronger bounded preload; CP-116.
  - EXP-084 proves the reset hook and client ordering work at runtime and pass CUA, but the experiment is INVALID because debugging attempts advanced the frozen epoch baseline before the final two-cycle run; CP-119.
  - EXP-085 executed exact 0 -> 1 -> 2 reset receipts and final joint convergence, but is INVALID because its test incorrectly required the asynchronous joint-state stream to be reset at service-return time; CP-120.
  - EXP-086 validly qualifies ResetWorld on a fresh changed-state stack with exact 0 -> 1 -> 2 step-zero receipts, fresh joint/controller convergence, fail-closed invalid keyframe, and CUA visual restoration; CP-121.
  - EXP-087 validly reaches CLOSE_READY and completes the first seating preload, but the first 2 mm arm increment does not physically lift the cup and the bilateral-contact monitor aborts; CP-122.
  - EXP-088 validly applies the final allowed 0.006 rad preload, but the second 2 mm increment raises the cup only 0.0119 mm and leaves table support; CP-123.
  - EXP-089 validly executes the frozen final 3 mm arm increment with negligible plan-to-execute drift, but the cup remains table-supported and its measured lift is effectively zero; CP-124.
  - EXP-090 is INVALID because the staged-approach invocation omitted the separately required --execute gate; the CLI failed closed before any robot action and the fresh physical baseline remains unchanged; CP-125.
  - EXP-091 validly reaches CLOSE_READY and proves the stiff mapping produces a safe 0.415 N transient right-pad contact, but the first q6 search command does not produce bilateral contact; CP-126.
  - EXP-092 validly proves 2 seconds of bilateral contact at q6=-0.04741 with at least 0.167 N summed normal force per side, under every force, displacement, provenance, and no-hidden-aid gate; CP-127.
  - EXP-093 validly executes the first 2 mm arm increment but the cup remains table-supported; transient bilateral-contact loss aborts the client monitor even though MoveIt and the controller report success; CP-128.
  - EXP-094 is INVALID because its intended 20 microradian command increment was incorrectly recomputed from constrained actual q6 each loop, causing non-convergent micro-creep; it was safely interrupted with all physical gates intact; CP-129.
  - EXP-096 validly sustains at least 0.50 N normal force per fingertip side for 2 seconds by preserving the accumulated gripper command reference; CP-131.
  - EXP-097 validly executes the frozen second 2 mm arm increment with negligible plan-to-execute drift and continuous bilateral contact, but the cup slips tangentially, rises only 0.001 mm, and remains table-supported; CP-132.
  - EXP-095 is INVALID because it reached the 0.50 N force target but its hold command reset the controller reference to constrained actual q6, unloading the pads to 0.494 N; CP-130.
  - EXP-096 validly sustains 0.511-0.515 N normal force per side for 2 seconds by preserving the accumulated command target, with all safety and provenance gates passing; CP-131.
disproven_routes:
  - The pre-isolation backup is provenance only and is not an implementation source; CP-001.
open_hypotheses:
  - The MuJoCo fingertip contacts are too compliant because only friction parity was mapped; explicitly mapping Gazebo's 1000000 N/m stiffness and 100 N s/m damping through MuJoCo direct-format solref will raise bounded pad normal force enough to carry the 20 g cup.
latest_checkpoint: CP-131
next_experiment: NONE
---

# SO-101 MuJoCo ROS 2 Migration Experiment Ledger

Raw logs, screenshots, videos, bags, and build artifacts belong only under the evidence root. The
ledger records conclusions and evidence references, never copied raw evidence. Experiments must use
the `PLANNED -> RUNNING -> VALID | INVALID` state transitions from the SO-101 development workflow.

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The behavior source can be migrated without a Gazebo Python runtime dependency and without weld or teleport shortcuts.
working_tree_status: Clean baseline plus the three Task 1 isolation deliverables pending their single scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - HEAD before the Task 1 commit is 45c6efc701b133c45875e86b0053cfc37dab7f4f.
  - The merge-base with origin/main is d300e7a41fb274d6d7e120699b7040666ea61904.
  - The protected Gazebo Python tree has no baseline difference or worktree status.
disproven_routes:
  - The rejected backup must remain read-only provenance and must not supply migration behavior.
open_risks:
  - No MuJoCo runtime experiment has run yet.
next_command: Define EXP-001 before the first runtime-affecting migration experiment.
```

## Checkpoint CP-038

```yaml
checkpoint_id: CP-038
last_valid_experiment: EXP-024
current_hypothesis: The pinned patch behavior is GREEN, but the overlay replay entry point is not idempotent for an already-applied zero-context patch and must be corrected before qualification can continue.
working_tree_status: HEAD 2346284e8cb9a6f32c9f676f078569da2adf26e0; index empty; fourteen preserved Task 10 implementation paths plus this ledger are dirty. The isolated dependency checkout contains only the three approved patched upstream paths, but the failed replay duplicated insertions in its plugin-base header and upstream test; its core source was restored to the intended content. No reset, clean, stash, commit, or push was performed.
owned_processes: NONE; the failed build command exited and no MuJoCo or ROS stack was launched.
preserved_processes: Host evidence continues to identify codex, kimi, and so101-py-qual as running and preserved; sandbox tmux visibility is unavailable and must not override the host evidence. No unrelated process or session was stopped.
confirmed_conclusions:
  - The approved documentation amendment is committed as 2346284e8cb9a6f32c9f676f078569da2adf26e0.
  - Executable RED was established before production changes: the pinned upstream test failed to compile because the snapshot virtual was absent, and support failed to compile because the plugin override was absent.
  - Focused GREEN passed for dependency replay contracts 10/10, upstream pause/snapshot behavior 2/2, and support atomic evidence 9/9.
  - The intended pinned checkout diff and repository patch matched SHA-256 fd2869212d40809dca70f4cc971f93215a64812900cc992817305a33dfcf971e before overlay qualification.
  - The overlay build then failed because build_reset_qualified_overlay.sh attempted to apply an already-applied --unidiff-zero patch again; duplicate virtual declarations are the decisive compiler boundary. Raw log SHA-256 is 084589ede9a7d9d667711d4937f8c5e2f26ff05f7223a875ebe2e87a7a49e384.
  - Gazebo protected-tree diff and status gates both remain zero; the main worktree index remains empty.
disproven_routes:
  - `git apply --unidiff-zero --check` cannot be used to distinguish a clean checkout from an already-applied insertion-only patch because it can accept a second insertion.
  - The failed overlay build cannot qualify runtime provenance or justify continuing to Task 10B.
open_risks:
  - The isolated dependency header and upstream test still contain only this turn's duplicate insertions and must be restored to exactly one approved copy without reset or clean.
  - The build script requires a behavior-tested already-applied branch before overlay qualification is rerun.
next_command: NONE; obtain explicit approval to remove only the duplicate copies created by the failed replay and add an executable idempotent-replay regression before changing build_reset_qualified_overlay.sh.
```

## Checkpoint CP-039

```yaml
checkpoint_id: CP-039
last_valid_experiment: EXP-024
current_hypothesis: The dedicated post-pause snapshot hook is reset-qualified and Task 10B can now consume only its paused step-zero evidence boundary.
working_tree_status: HEAD 2346284e8cb9a6f32c9f676f078569da2adf26e0; Task 10A's patch, lock, build/check scripts, dependency test, support header/cpp/test, and this ledger are ready for one scoped commit. Pre-existing package/observer/reset paths remain unstaged for Task 10B.
owned_processes: NONE; only builds and tests ran, and no MuJoCo ROS stack or tmux session was started.
preserved_processes: Host evidence continues to identify codex, kimi, and so101-py-qual as running and preserved; no unrelated process or session was stopped.
confirmed_conclusions:
  - Explicit user authorization restored exactly the three pinned checkout paths to one approved copy; checkout diff SHA-256 is fd2869212d40809dca70f4cc971f93215a64812900cc992817305a33dfcf971e.
  - Replay idempotence RED failed with duplicate diff SHA 32af4dfa...; GREEN passed after the build script distinguished an exact already-applied diff before attempting zero-context apply. RED log SHA-256 5a909558f8667bf7ac74cb265100d9b78452156e97f33569b809d69279bf9b3d; GREEN log SHA-256 774fa5fd1a962d190b3b9cef91c898268681218542619fcd34cdec6ddb403a12.
  - Pinned upstream build and tests passed 116 tests with zero failures/skips; overlay log SHA-256 1a6dc1e8020df323843eb53af42308fe1860e81574734fa0805da1094b257d95.
  - Runtime provenance verified URL, tag 0.0.3, commit 35ba8174b62d9560093614f981a3d4b978a96036, patch SHA, overlay-first prefixes, exact header, and runtime hashes; evidence SHA-256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1.
  - Support snapshot tests pass 9/9, both project package tests report 363 tests, zero errors/failures, and four opt-in skips; aggregate result SHA-256 8f845b322ee9dcd34f180636fcfd9beb2a29f3fc8464b5db130edcda86bdfe5c.
  - Ruff, clang-format dry-run, dependency isolation, diff-check, and both Gazebo protected-tree gates pass.
disproven_routes:
  - Reapplying an insertion-only zero-context patch after exact-diff recognition is unsafe and is now regression-tested.
  - Running update cannot publish or consume a pending reset generation; publisher contention cannot consume it either.
open_risks:
  - Task 10B transactional Python behavior and EXP-031 live qualification remain unverified.
next_command: Create the scoped Task 10A commit, then begin Task 10B RED tests without running EXP-031 until all offline gates pass.
```

## Experiment EXP-031

```yaml
experiment_id: EXP-031
prior_experiment: EXP-030
status: VALID
lifecycle: FULL_RESTART
hypothesis: The qualified dedicated post-pause snapshot hook lets two task_start transactions each return exactly one new paused step-zero epoch while independent fresh joint/controller feedback meets the unchanged reset tolerances, and an invalid keyframe changes no epoch and leaves the world paused.
independent_variable: Execute the approved Transactional Pause/Reset/Snapshot path against the qualified pinned overlay; no StepSimulation call is permitted.
controlled_variables: Simulation only; HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab plus eight unstaged Task 10B paths; ROS_DOMAIN_ID 112; session exp031-snapshot-domain112; source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; upstream https://github.com/ros-controls/mujoco_ros2_control tag 0.0.3 commit 35ba8174b62d9560093614f981a3d4b978a96036; patch SHA-256 fd2869212d40809dca70f4cc971f93215a64812900cc992817305a33dfcf971e; installed header SHA-256 688337291e7e1d340daf9ffe36fe8c6ed72f085f1ddf302215e5a4a8a35386dc; runtime hashes are pinned in dependency-lock.yaml and verified by check_reset_qualified_runtime.py.
acceptance_criteria: Domain 112 starts and ends empty with no daemon; readiness proves both MuJoCo services, exactly three named active controllers, and an evidence publisher/subscriber; two task_start receipts each increment epoch exactly once with simulation_step=0 and paused=true atomic finite object pose/twist/contact; object error <=0.003 m; each of six independently sampled fresh joints <=0.002 rad; controllers active; final paused; invalid keyframe leaves epoch unchanged and fails paused; provenance, ownership, logs, exit codes, hashes, and cleanup are complete.
invalid_criteria: Provenance mismatch, nonempty initial domain, readiness failure, incomplete/corrupt evidence, unbound process ownership, hash failure, or polluted cleanup makes the measurement INVALID. With those prerequisites valid, any reset assertion failure is a VALID behavioral failure and stops further work.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-031/
domain_id: 112
domain_preregister_no_daemon_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
owned_processes: Reserved task-owned tmux session so101-mujoco-exp031; not started at PLANNED registration.
preserved_processes: codex, kimi, and so101-py-qual observed running and preserved; no unrelated process/session may be stopped.
result: Behavioral failure. Provenance, empty-domain, launch, readiness, ownership, evidence hashing, task-session cleanup, and final no-daemon cleanup were valid. The first task_start transaction reached the expected new-epoch step-zero paused evidence branch but failed the independent fresh six-joint convergence gate; pytest exit 1. The second reset and invalid-keyframe case did not run because the valid product failure is a mandatory stop.
next_command: NONE
```

## Checkpoint CP-040

```yaml
checkpoint_id: CP-040
last_valid_experiment: EXP-031
current_hypothesis: NONE; EXP-031 is a VALID controlled experiment with a Task 10B behavioral failure at independent joint convergence, so thresholds/order/timeout and production code must not be changed without new authorization.
working_tree_status: HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab; index empty; exactly eight Task 10B paths remain unstaged (ledger, package.xml, observer.py, test_mujoco_observer.py, new client.py/reset.py/test_mujoco_reset.py/test_reset_live_contract.py). No Task 10B commit was created.
owned_processes: NONE; so101-mujoco-exp031 was the only task-owned tmux session and was stopped successfully. ROS_DOMAIN_ID 112 is empty by both driver cleanup and post-verification no-daemon checks.
preserved_processes: codex, kimi, and so101-py-qual were observed before the run and preserved; no unrelated session/process was stopped.
confirmed_conclusions:
  - EXP-031 prerequisites were valid: domain_before_rc=0, launch_rc=0, readiness_rc=0, kill_rc=0, domain_cleanup_rc=0, and hash_rc=0. Exactly three named controllers became active, both MuJoCo services were present, and the evidence publisher plus one-message subscription were ready.
  - pytest_rc=1 is therefore a VALID behavioral failure, not an INVALID measurement. Driver exit is 1 and enters the failure denominator.
  - Control flow reached the exact expected epoch, publisher-sequence advance, simulation_step=0, and paused=true checks before failing `joint convergence failed`; the failure is independent controller feedback, not an atomic joint field. The test did not persist an exact failing joint vector, so no numeric diagnosis or threshold inference is authorized.
  - Failure handling issued pause(true), the live test finally path issued pause(true), only the named task session was killed, and domain 112 ended empty. Final domain file SHA-256 is e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.
  - Evidence hashes: launch 8025db75657c41c004217d7be3882ae2da13e9c04a40830a9ecb9d2481c0c4d8; readiness 9db5899089debddfbc9db936b6f82a86c6297a7417d59782d58f8f45ea64e96c; live pytest 6a400b7dd5b3d549b8f3a354e7db7a05f8a24a5e0e4bfaba1e565bc3885a9a9c; driver f1b31eb456b24d4f37be0c0298b0d249e6ebc79a8253f6f449400e9df4046391; exit-codes 0a22d06b564fadffcb4a1518ac67ded04e83155cf418c7e0abd0cc2726fc685a.
  - Gazebo protected-tree diff/status gates remain zero and the repository index is empty.
disproven_routes:
  - Offline GREEN and a qualified snapshot hook do not establish Task 10 reset success without independent fresh joint convergence.
  - This valid failure cannot be relabeled INVALID merely because the exact failing joint vector was not emitted; the controlled assertion itself failed after valid prerequisites. It also cannot justify changing the 0.002 rad threshold, transaction order, or 10 s deadline.
open_risks:
  - Whether the failure was stale independent feedback or a genuine >0.002 rad joint error is not distinguished by persisted evidence.
  - The second task_start reset, invalid-keyframe epoch stability, and full four-pause-window series remain unexecuted because the first valid behavioral failure required an immediate stop.
next_command: NONE; await orchestrator review and explicit new architecture/diagnostic authorization.
```

## Experiment EXP-032

```yaml
experiment_id: EXP-032
prior_experiment: EXP-031
status: VALID
lifecycle: FULL_RESTART
hypothesis: The first EXP-031 joint failure is caused by callback-count freshness accepting a queued or otherwise non-post-reset joint sample; a boundary-correlated trace will distinguish that case from a genuinely post-reset joint vector outside the unchanged 0.002 rad gate.
independent_variable: Diagnostic observation only. Record every joint callback message stamp, receive time, callback count, six-joint vector, and reset/pause/controller boundary while executing one unchanged task_start transaction.
controlled_variables: Simulation only; HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab plus the same eight unstaged Task 10B paths; source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; upstream and qualified patch unchanged; ROS_DOMAIN_ID 113; session exp032-joint-freshness-domain113; reset order, 10 s deadline, object tolerance 0.003 m, and per-joint tolerance 0.002 rad unchanged; no StepSimulation.
success_criteria: A complete trace binds the reset return callback-count baseline and every later joint sample to message stamp, receive time, exact vector, and transaction boundary, while preserving valid launch/readiness/provenance/ownership/cleanup evidence. The trace must distinguish pre-reset queued feedback from genuinely post-reset feedback and report the exact maximum joint error.
invalid_criteria: Nonempty initial domain, readiness/provenance failure, missing boundary or joint trace, unbound ownership, incomplete cleanup, or missing evidence hash.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-032/
domain_id: 113
owned_processes: Reserved task-owned tmux session so101-mujoco-exp032; not started at PLANNED registration.
preserved_processes: codex, kimi, and so101-py-qual must remain untouched.
result: The diagnostic validly reproduced the first-reset failure and disproved the queued-callback acceptance hypothesis. ResetWorld returned at callback count 6, and no callback occurred afterward through resume, activate, re-pause, or the convergence check. The reported vector was therefore the pre-reset message at simulation stamp 6.317999999 s, with max absolute error 1.0973360446 rad. Resume-to-re-pause lasted about 3.57 ms, shorter than the configured 100 Hz joint-state period of 10 ms, so the transaction could not obtain independent post-reset feedback before pausing.
evidence:
  - joint_boundary_trace_sha256: 5111d2d95d024ab89c8c196e07e67fa8fd18d06ffc48d3be485d58bccea77551
  - launch_sha256: 4906039c7c621956cec5aa22fb904969bd2d55eebdf81693bc9c96bf6b56d8fa
  - readiness_sha256: 861ac6cc06dd0e14bca1214c1f457d10d06fabb6a089150789e1d57e1dd59492
  - diagnostic_sha256: 4d52cbb3f7d483aeac26475bfbd441b04b61e97dedaf40044dd6ab43db6936c8
  - domain_after_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
exit_codes: domain_before_rc=0 launch_rc=0 readiness_rc=0 diagnostic_rc=0 kill_rc=0 domain_cleanup_rc=0 hash_rc=0
next_command: Add a RED contract that bounded resume must receive at least one post-reset joint callback before the authoritative re-pause snapshot.
```

## Checkpoint CP-041

```yaml
checkpoint_id: CP-041
last_valid_experiment: EXP-031
current_hypothesis: Callback execution count alone may misclassify queued joint feedback as post-reset fresh; EXP-032 will test this without changing transaction behavior.
working_tree_status: HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab; index empty; the same eight Task 10B paths are unstaged, with only this ledger registration added.
owned_processes: NONE
preserved_processes: codex, kimi, and so101-py-qual remain running and must not be stopped.
confirmed_conclusions:
  - EXP-031 remains a VALID behavioral failure at independent joint convergence.
  - The existing evidence does not contain the failing joint vector and cannot distinguish stale feedback from physical error.
  - Source inspection shows the joint subscriber is spun outside the synchronous service calls and freshness is currently only callback_count > count captured after ResetWorld returns.
open_risks:
  - A callback executed after reset can still carry a message published before reset.
  - A genuinely post-reset sample may instead exceed the unchanged tolerance; only the correlated trace may decide.
next_command: Execute EXP-032 on fresh confirmed-empty ROS_DOMAIN_ID 113 with no production change.
```

## Checkpoint CP-042

```yaml
checkpoint_id: CP-042
last_valid_experiment: EXP-032
current_hypothesis: The Task 10B failure is caused by re-pausing before one 100 Hz post-reset joint sample can arrive; waiting within the existing bounded-resume phase for callback_count to advance should provide fresh independent feedback without changing service order, thresholds, or the 10 s transaction deadline.
working_tree_status: HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab; index empty; the same eight Task 10B paths are unstaged, with EXP-032 results added only to the ledger.
owned_processes: NONE; so101-mujoco-exp032 was stopped and ROS_DOMAIN_ID 113 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain untouched.
confirmed_conclusions:
  - EXP-032 is VALID: all launch, readiness, diagnostic, ownership, hash, and cleanup gates passed.
  - No post-reset joint callback occurred. Callback count was 6 at ResetWorld return and remained 6 at convergence evaluation.
  - The failure vector was the last pre-reset sample at stamp 6.317999999 s: [0.0008834752, 1.0973360446, 0.4145440286, 0.0868216906, 0.0001103944, 0.0008648286] rad.
  - Resume-to-re-pause was about 3.57 ms, below the 10 ms publication period configured by the 100 Hz joint-state broadcaster.
  - The per-joint 0.002 rad threshold was never applied to a fresh post-reset vector, so EXP-031 does not prove a physical reset miss.
disproven_routes:
  - The observed failure was not a queued callback incorrectly accepted as fresh; there was no callback-count advance at all.
  - Changing the 0.002 rad threshold cannot fix absence of feedback and remains forbidden.
next_command: Establish a focused RED service-boundary test requiring fresh callback arrival during bounded resume before re-pause, then implement the minimum wait under the original deadline.
```

## Experiment EXP-033

```yaml
experiment_id: EXP-033
prior_experiment: EXP-032
status: VALID
lifecycle: FULL_RESTART
hypothesis: Waiting inside the existing bounded-resume phase until one post-reset joint callback arrives lets the unchanged transaction re-pause on authoritative step-zero atomic evidence and independently verify all six joints within 0.002 rad for two resets, while invalid keyframe failure remains paused with no epoch change.
independent_variable: The minimum Task 10B code change waits for joint_callback_count to advance after ResetWorld and controller activation before re-pause; no service is added, removed, or reordered.
controlled_variables: Simulation only; HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab plus the same eight unstaged Task 10B paths; source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; qualified upstream URL/tag/commit/patch/runtime unchanged; ROS_DOMAIN_ID 114; session exp033-bounded-resume-domain114; 10 s transaction deadline; object tolerance 0.003 m; per-joint tolerance 0.002 rad; no StepSimulation, hardware, GUI, MoveIt, or workflow motion.
acceptance_criteria: Domain 114 starts and ends empty with no daemon; launch/readiness proves both MuJoCo services, exactly three named active controllers, and evidence publication; two task_start receipts increment epochs sequentially by one with simulation_step=0 and paused=true finite atomic object evidence; each has independent post-reset six-joint feedback within 0.002 rad and active controllers; invalid keyframe changes no epoch and leaves paused; ownership, logs, exits, hashes, and cleanup are complete.
invalid_criteria: Provenance mismatch, nonempty initial domain, readiness failure, missing evidence, unbound ownership, hash failure, or polluted cleanup. With valid prerequisites, any reset assertion failure is a VALID behavioral failure and stops further work.
prequalification:
  focused_reset_tests: 18 passed; sha256 729498e5bb74791c449bd81daae53960afaea75639e4957a5f7dd233cc52234e
  non_live_tests: 116 passed and 2 skipped; sha256 3a71be37eca9908f2b3fa3525bdfa1126bd9dae5e19ad36160f16d491e02f12d
  ruff: lint and format passed with pinned 0.15.20; sha256 f63e6c4d2361553eeaa610cd347061625231482c4967f50df631e7af3254a879
  aggregate: 368 tests, zero failures, four skips; sha256 713e33e96081d8569f1e53fa1aab4addb54e7e12a6fe490fe1c779f27f573dcc
  runtime_provenance_sha256: b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1
evidence_path: /tmp/so101-debug-mujoco-migration/exp-033/
domain_id: 114
domain_preregister_no_daemon_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
owned_processes: Reserved task-owned tmux session so101-mujoco-exp033; not started at PLANNED registration.
preserved_processes: codex, kimi, and so101-py-qual observed and must remain untouched.
result: Behavioral success. Two task_start transactions returned sequential epochs 0->1 and 1->2 with simulation_step=0, authoritative paused=true atomic snapshots, finite object state within 0.003 m, active controllers, and independent post-reset joint vectors within 0.002 rad. The two post-reset maximum joint errors were approximately 0.000650087 rad and 0.000195667 rad. The invalid keyframe left epoch 2 unchanged and failed paused. All environment, readiness, ownership, pytest, hash, and cleanup exits were zero.
evidence:
  - launch_sha256: 432efd6ff7f0edaf938b92ae454794d62456beaa5cfa6930bb6bf7b15ffbdfe2
  - live_reset_contract_sha256: da19e389cf42928d24a7933c3fb78cc7313a212031b9eebf9144347f03d33dcc
  - controllers_readiness_sha256: ffb97138b19ea06a4a856c713c3987ef61218efd82b6cbda47eef9837da177cc
  - evidence_topic_readiness_sha256: 93ffd4380a1d3802c5b29091366f5ae99edec8f4701daf2a44969aed1698d817
  - evidence_subscriber_readiness_sha256: 50c4869e7db6d2208ba0e27aeb81d6bfc63576bfbd7ac0d0919b0464dbaf5b3a
  - exit_codes_sha256: 2264f485e5ba95fec6367ef74346dba711e53881a49d9113a1fbbc732c27d467
  - domain_after_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
exit_codes: domain_before_rc=0 launch_rc=0 readiness_rc=0 pytest_rc=0 kill_rc=0 domain_cleanup_rc=0 hash_rc=0
next_command: Run the final Task 10 qualification gates and create the scoped Task 10B commit.
```

## Checkpoint CP-043

```yaml
checkpoint_id: CP-043
last_valid_experiment: EXP-032
current_hypothesis: The bounded-resume freshness wait fixes the measured absence of post-reset joint feedback without changing transaction order or acceptance thresholds; EXP-033 will qualify the full two-reset and invalid-keyframe contract.
working_tree_status: HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab; index empty; exactly eight Task 10B paths remain unstaged; protected Gazebo diff/status gates are zero.
owned_processes: NONE; ROS_DOMAIN_ID 114 is confirmed empty and so101-mujoco-exp033 is reserved but not started.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched.
confirmed_conclusions:
  - The focused RED failed at joint convergence before a post-reset callback; the minimum bounded-resume wait made it GREEN.
  - Focused reset tests pass 18/18, non-live tests pass 116 with two live skips, Ruff passes, rebuild/provenance pass, and aggregate package tests report 368 tests with zero failures and four skips.
  - No StepSimulation call exists in the reset qualification path.
next_command: Execute EXP-033 on fresh ROS_DOMAIN_ID 114, then classify it strictly as INVALID environment/evidence or VALID behavioral success/failure.
```

## Checkpoint CP-044

```yaml
checkpoint_id: CP-044
last_valid_experiment: EXP-033
current_hypothesis: NONE; Task 10B's transactional reset contract is live-qualified after fixing the bounded-resume feedback boundary.
working_tree_status: HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab; index empty; exactly eight Task 10B paths remain unstaged pending final gates and one scoped commit; protected Gazebo diff/status gates remain zero.
owned_processes: NONE; so101-mujoco-exp033 was stopped and ROS_DOMAIN_ID 114 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched.
confirmed_conclusions:
  - EXP-033 is a VALID behavioral success with every prerequisite and cleanup exit zero.
  - Reset receipts were 0->1 and 1->2, both step zero and paused; invalid keyframe preserved epoch 2 and left the world paused.
  - First and second post-reset joint vectors had maximum absolute errors about 0.000650087 rad and 0.000195667 rad, respectively, below the unchanged 0.002 rad gate.
  - Final independent joints after the invalid-keyframe path remained within the gate, with maximum absolute value about 0.001810608 rad.
  - The accepted fix changes only timing inside bounded resume: it waits for one post-reset joint callback under the original deadline, then re-pauses. Service order, 10 s deadline, thresholds, snapshot semantics, and no-StepSimulation boundary are unchanged.
disproven_routes:
  - EXP-031 did not demonstrate physical reset failure; it failed because no post-reset joint feedback arrived before re-pause.
  - Pre-reset safety-pause joint state is not a reset result and must not be evaluated against the post-reset joint target.
next_command: Run final Task 10A Step 7 and Task 10B Step 9 gates, then commit only the eight Task 10B paths.
```

## Experiment EXP-034

```yaml
experiment_id: EXP-034
prior_experiment: EXP-033
status: VALID
lifecycle: FULL_RESTART
hypothesis: Rejecting incomplete or nonfinite joint messages before advancing the freshness counter preserves the successful EXP-033 reset behavior while closing the stale-vector acceptance gap.
independent_variable: The joint callback now advances freshness and replaces cached positions only after all named joints 1 through 6 are present and finite.
controlled_variables: Simulation only; HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab plus the same eight unstaged Task 10B paths; qualified overlays unchanged; ROS_DOMAIN_ID 115; session exp034-valid-joint-domain115; transaction order, 10 s deadline, 0.003 m object tolerance, 0.002 rad joint tolerance, and no-StepSimulation rule unchanged.
acceptance_criteria: Repeat the complete EXP-033 two-reset and invalid-keyframe contract with valid environment/readiness/ownership/hash/cleanup evidence; both post-reset joint samples must remain complete, finite, fresh, and within threshold.
invalid_criteria: Provenance mismatch, nonempty initial domain, readiness failure, incomplete evidence, unbound ownership, hash failure, or polluted cleanup. With valid prerequisites, any product assertion failure is a VALID behavioral failure.
prequalification:
  joint_validity_red: Expected callback-count assertion failed; sha256 5dd506eaac48d12a9817c47968ef96832a1424944cbde0acbc5a7f494f432a32
  reset_green: 19 passed; sha256 ee4eff9889e1af5d58afcf5b1c9bcf2256a62d5353c3298747e6b8add680dd05
  non_live: 117 passed and 2 skipped; sha256 0344df57e80ac2466a8c7fba37592fd830d94e1d2018ba68ac61b49548a86554
  ruff: passed; sha256 f63e6c4d2361553eeaa610cd347061625231482c4967f50df631e7af3254a879
  aggregate: 369 tests, zero failures, four skips; sha256 d5ce6e3f5b0496eccabef5097ada8c27aa8582819a7555e4b7422c750a35b87f
  provenance_sha256: b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1
evidence_path: /tmp/so101-debug-mujoco-migration/exp-034/
domain_id: 115
domain_preregister_no_daemon_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
owned_processes: Reserved task-owned tmux session so101-mujoco-exp034; not started at PLANNED registration.
preserved_processes: codex, kimi, and so101-py-qual remain untouched.
result: Behavioral success. The exact current source repeated sequential reset epochs 0->1 and 1->2 with step-zero authoritative paused snapshots, complete finite post-reset joint feedback, active controllers, and object/joint thresholds unchanged. The two post-reset maximum joint errors were approximately 0.000650087 rad and 0.000390691 rad. Invalid keyframe preserved epoch 2 and left the world paused. All environment, readiness, pytest, ownership, hash, and cleanup exits were zero.
evidence:
  - launch_sha256: ab8d8432f8a554d35260d541dd00c724fd73ef4f20cfe7122c43851c4fd650fb
  - live_reset_contract_sha256: 3e54ae368e16c03e14ca68ea18ea65eee5a0f24063d806acc6c9765d59154cad
  - controllers_readiness_sha256: 7a77a1a30f36e653f8069ae0f3dbf8d9becc0126d605ad632dec60a4edc4006e
  - evidence_topic_readiness_sha256: 86581877ae770a83490e38412744ed88d0656782fd5b9831944f7c6730e06e6f
  - evidence_subscriber_readiness_sha256: b655173e77fef5f270bddbb4cee0514bd21328ae8a6b8b1d4bce68b7ba25ac16
  - exit_codes_sha256: 2264f485e5ba95fec6367ef74346dba711e53881a49d9113a1fbbc732c27d467
  - domain_after_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
exit_codes: domain_before_rc=0 launch_rc=0 readiness_rc=0 pytest_rc=0 kill_rc=0 domain_cleanup_rc=0 hash_rc=0
next_command: Run final ledger-aware gates, then create and push the scoped Task 10B commit.
```

## Checkpoint CP-045

```yaml
checkpoint_id: CP-045
last_valid_experiment: EXP-033
current_hypothesis: Valid-only callback accounting closes the freshness loophole without changing the live reset outcome; EXP-034 will prove the exact current source.
working_tree_status: HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab; index empty; exactly eight Task 10B paths remain unstaged; Gazebo gates remain zero.
owned_processes: NONE; ROS_DOMAIN_ID 115 is confirmed empty and so101-mujoco-exp034 is reserved but not started.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched.
confirmed_conclusions:
  - RED proved an incomplete one-joint message incorrectly advanced the old freshness counter.
  - GREEN accepts only complete finite six-joint feedback; 19 focused reset tests, 117 non-live tests, Ruff, build, provenance, 369 aggregate tests, isolation, and Gazebo gates pass.
next_command: Execute EXP-034, then rerun final lightweight gates and create the scoped Task 10B commit.
```

## Checkpoint CP-046

```yaml
checkpoint_id: CP-046
last_valid_experiment: EXP-034
current_hypothesis: NONE; Task 10B is implementation- and runtime-qualified on the exact current source.
working_tree_status: HEAD 79644714c9d551d5134496f8f5c7eef17b31e5ab; index empty; exactly eight Task 10B paths remain unstaged pending final ledger-aware gates and the scoped commit; protected Gazebo gates remain zero.
owned_processes: NONE; so101-mujoco-exp034 was stopped and ROS_DOMAIN_ID 115 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched.
confirmed_conclusions:
  - The root cause of EXP-031 was absence of any post-reset joint callback during a 3.57 ms resume window, shorter than the 100 Hz feedback period.
  - The minimum fix waits for one valid complete finite post-reset joint message within the original deadline before re-pause; it does not change service order, thresholds, snapshot semantics, or call StepSimulation.
  - EXP-033 qualified the bounded-resume fix, and EXP-034 qualified the final valid-only joint freshness implementation.
  - Final pre-live gates report 19 focused reset tests, 117 non-live tests with two live skips, Ruff pass, exact overlay provenance, 369 aggregate tests with zero failures and four skips, isolation pass, and protected Gazebo zero diff/status.
  - EXP-034 reports two successful reset epochs, post-reset maximum joint errors about 0.000650087 and 0.000390691 rad, valid step-zero paused atomic evidence, and invalid-keyframe epoch stability/final pause.
open_risks:
  - The invalid-keyframe failure contract does not require the independently drifting joints to remain inside the successful-reset threshold after failure; only epoch stability and final pause are asserted there.
next_command: Run final ledger-aware non-live/Ruff/isolation/diff/Gazebo/domain gates, then stage exactly eight Task 10B paths, commit, and push the branch.
```

## Checkpoint CP-037

```yaml
checkpoint_id: CP-037
last_valid_experiment: EXP-024
current_hypothesis: The user-approved dedicated post-pause state snapshot hook can publish the pending reset generation as an authoritative step-zero paused object snapshot without advancing physics or conflating asynchronous joint feedback with atomic evidence.
working_tree_status:
  head: e0838b0b8d76ee17620a998931fa57718b0b284d
  staged_paths: NONE
  preserved_dirty_paths:
    - docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
    - src/so101_mujoco_demo_py/config/dependency-lock.yaml
    - src/so101_mujoco_demo_py/package.xml
    - src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch
    - src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py
    - src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/observer.py
    - src/so101_mujoco_demo_py/test/test_mujoco_observer.py
    - src/so101_mujoco_demo_py/test/test_reset_qualified_dependency.py
    - src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp
    - src/so101_mujoco_support/src/simulation_evidence_plugin.cpp
    - src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp
    - src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/client.py
    - src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py
    - src/so101_mujoco_demo_py/test/test_mujoco_reset.py
    - src/so101_mujoco_demo_py/test/test_reset_live_contract.py
  documentation_only_additions_this_checkpoint:
    - docs/superpowers/specs/2026-08-09-so101-mujoco-ros2-migration-design.md
    - docs/superpowers/plans/2026-08-09-so101-mujoco-ros2-migration.md
owned_processes: NONE
preserved_processes: The Mac orchestrator independently observed codex, kimi, and so101-py-qual running on the same ai-station with `tmux list-sessions`; all three were preserved, and none was started, stopped, signaled, or cleaned during this documentation-only amendment. Remote sandbox visibility does not override that host-level observation.
approval_correction:
  - The user approved a source-compatible default no-op on_state_snapshot(const mjModel *, const mjData *, bool paused) hook in pinned upstream 0.0.3, dispatched once per initialized plugin under sim_mutex_ after every successful or idempotent SetPause(true), and never for pause false or failed requests.
  - Snapshot dispatch uses authoritative mj_data_, is read-only, is not generic update(), does not advance physics, and does not write qpos/qvel/ctrl/xfrc/constraint.
  - A running update must retain pending reset generation. Only successful publisher-lock acquisition in on_state_snapshot(..., true) consumes it and publishes old+1, step zero, paused true; contention retains it for a typed-EvidenceStale-driven idempotent re-pause retry inside the unchanged 10 s deadline.
  - The Task 10 transaction is running strict deactivate -> pause -> ResetWorld(task_start) -> bounded resume -> strict activate -> re-pause snapshot -> atomic object plus independent joint/controller verification. It no longer calls StepSimulation(1).
confirmed_conclusions:
  - CP-036/EXP-030 establishes the need for the dedicated hook: generation was consumed during activate as paused=false, and paused stepping did not create the required authoritative paused snapshot.
  - Atomic evidence contains object pose/twist/contact from one locked physics snapshot. Joint positions remain nearest/fresh asynchronous /joint_states controller feedback and are never represented as an atomic message field or same-boundary correlation.
  - Task 10 thresholds remain object position error <=0.003 m and each of six independent joint errors <=0.002 rad, with the original 10 s deadline. Stricter final-release postconditions remain separate and unchanged.
disproven_routes:
  - StepSimulation(1) must not be used to wake Task 10 reset evidence; it advances physics and EXP-030 showed it does not supply the missing paused atomic publication.
  - SetPause must not invoke every plugin's generic update(), and running update must not consume a pending reset generation.
open_risks:
  - The pinned upstream callback currently has no snapshot hook; sim_mutex_ placement, success/idempotent call counts, failure-path exclusion, and authoritative mj_data_ must first be proven by RED contracts.
  - Realtime publisher contention must demonstrably preserve generation and permit only typed EvidenceStale idempotent re-pause retry within the unchanged deadline.
  - No Task 10A/10B implementation, build, package test, or EXP-031 runtime qualification is authorized by this documentation-only checkpoint.
next_command: Review the CP-037 spec/plan documentation diff; after explicit implementation handoff, begin Task 10A Step 1 RED tests.
```

## Checkpoint CP-007

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-001
current_hypothesis: The independent MJCF can preserve the repository robot's six-joint kinematics and stable evidence names.
working_tree_status: Clean at Task 5 implementation commit 9b951ced787c418364a8304b0160ecdf2a5ba73c; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - Immutable ObjectState, ContactEvidence, SimulationEvidence, and ResetReceipt types implement the expanded atomic schema and ordering key.
  - WorldObserver.snapshot and WorldReset.reset expose no call-site freshness or session overrides.
  - Provenance entries resolve only against behavior source commit 8d7913e7f552a40ee627d65be8b873ac16748bc9 with verified source hashes and new-package destinations.
  - Package-level colcon test passed 63 tests with zero errors, failures, or skips; Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - Provenance source paths cannot be restricted to behavior_source.paths alone; exact adaptation source_path fields are required and now validated against the declared set.
  - Ruff invocation cannot inherit caller cwd because import classification changes; the executable gate now fixes cwd to the package root.
open_risks:
  - No MJCF has compiled or passed URDF parity yet.
next_command: Start Task 6 with MJCF compile and model-parity RED tests.
```

## Checkpoint CP-008

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-001
current_hypothesis: The independent deterministic scene can add the task object and table without weakening the verified robot-model parity contract.
working_tree_status: Clean at Task 6 implementation commit 1f73813ae79665562692158400ac2a62b8269e5b; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent MJCF compiles and exposes joints 1 through 6, stable robot body and geom names, fingertip collision geoms, six actuators, the so101_tcp site, and a home keyframe without weld, equality, adhesion, mocap, teleport, or direct object state writes.
  - Eleven deterministic URDF/MJCF FK samples passed with maximum position error 4.484050470211362e-16 m and maximum orientation error 0.0 degrees, below the declared 0.0005 m and 0.2 degree limits.
  - The package owns and installs its URDF, MJCF, model-parity configuration, and 43 versioned STL files; every copied input records an exact behavior-source path and SHA-256 in provenance.
  - Package-level colcon test passed 69 tests with zero errors, failures, or skips, including the real fail-closed Ruff integration; Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - Flattening fixed and moving fingertip collision mesh basenames is ambiguous; distinct fixed_fingertip_pad_collision and moving_fingertip_pad_collision names are required.
  - A repository-relative Xacro object-config argument is not cwd-stable because Xacro resolves it below the URDF directory; the copied deterministic robot URDF is therefore produced offline and installed as an owned asset.
open_risks:
  - The task object, table, deterministic reset keyframes, and collision-free scene feasibility are not yet implemented or verified.
next_command: Start Task 7 with RED tests for the independent task scene and deterministic keyframes.
```

## Checkpoint CP-009

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-001
current_hypothesis: The initial uncalibrated MuJoCo contact inputs do not yet prove a stationary free cup over the required ten-second headless run.
working_tree_status: Dirty Task 7 RED/GREEN work is intentionally preserved and uncommitted; no files are staged.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, so101-py-qual, and so101-physical-cpp-gui-019; no session or process was stopped.
confirmed_conclusions:
  - The independent scene compiles, contains a fixed table and free-joint cup, and reaches 10.000000000000009 simulated seconds with a finite 26-element time/qpos/qvel state.
  - The structural no-hidden-grasp tests pass: no equality, weld, adhesion, mocap body, cup actuator, or production object qpos/qvel write path is present.
  - The stationary-cup gate fails: displacement from 2 to 10 seconds is 4.034323607231733e-05 m and final translational speed is 0.009015012052262135 m/s, both above the provisional 1.0e-05 limits.
disproven_routes:
  - The first uncalibrated table/cup contact inputs cannot be accepted as stationary without a controlled diagnosis.
open_risks:
  - EXP-002 was not entered as PLANNED before the first headless execution; the run is diagnostic evidence only and cannot be promoted to VALID.
  - The failed speed may be contact/integration residual or an indexing defect; neither has been isolated.
next_command: NONE
```

## Experiment EXP-024

```yaml
experiment_id: EXP-024
status: VALID
prior_experiment: EXP-023
hypothesis: The frozen transaction's joint failure first appears either during the resume/activate window, during paused bounded stepping, or only in a stale joint-state cache; boundary-correlated callback counts and positions can distinguish these without changing production behavior.
prediction: Continuous observer/joint executors around one unchanged task_start transaction identify the first service boundary where joints 2/3/4 exceed 0.002 rad and show whether joint callback count advances after re-pause/step. If count is unchanged, the verification sample is stale; if it advances and error first crosses at a specific running boundary, that boundary owns the physical drift.
single_variable: Diagnostic measurement only: continuous background subscription capture with before/after snapshots at each existing service call. Model, overlay, transaction order, service timeout, 20-step count, reset thresholds, controllers, and initial state remain identical to EXP-023.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD d93bba347c2dbd5794c223a9e88f976286a736a8 plus the same eight dirty Task 10 paths and installed two-package build.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; exact lock/provenance pass.
  - Fresh task-owned ROS_DOMAIN_ID 106 and session exp024-joint-boundary-domain106; no MoveIt, GUI, workflow motion, or hardware.
success_criteria:
  - Every service boundary records monotonic time, result, controller/joint callback counts, six finite joint positions, and fresh atomic epoch/step/paused/object state when available.
  - The record distinguishes resume/activate drift, paused-step drift, and stale-cache explanations at the first divergent boundary.
failure_criteria:
  - The unchanged transaction still fails, but complete boundary evidence identifies where and whether the measured joints are fresh; this is a valid diagnostic failure.
invalid_criteria:
  - Missing boundary record, stale build/prefix, domain contamination, source-order mismatch, background executor failure, or incomplete task-owned cleanup.
provenance:
  source_commit: d93bba347c2dbd5794c223a9e88f976286a736a8 plus preserved eight Task 10 paths
  dependency_overlay: /data/work/ws_mujoco_ros2_control_003/install
  project_install: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 106
  gz_partition: NONE
  evidence_path: /tmp/so101-debug-mujoco-migration/exp-024/
commands:
  - command: Fresh headless stack plus /tmp/so101-debug-mujoco-migration/exp-024/joint_boundary_diagnostic.py
    exit_code: 0
observed:
  - Immediately after controller activation, joint callback count was 80 and maximum absolute joint position was 0.00006532658933886562 rad.
  - Immediately before paused StepSimulation(20), callback count remained 80 and the joint state remained within 0.000066 rad of zero.
  - Immediately after StepSimulation(20), joint callback count advanced from 80 to 84, evidence callback count advanced from 76 to 80, reset_epoch advanced from 0 to 1, and simulation_step was 3.
  - The fresh post-step joint state was [-0.00004523, 0.0127050914, 0.0144914167, 0.00273654045, 0.00000349, -0.00004194] rad; maximum absolute error was 0.0144914167 rad.
  - Controllers were active at the final sample; the task-owned stack was fully reaped and domain 106 was empty after cleanup.
inferred:
  - The stale-joint-cache hypothesis is disproven because both joint and evidence callback counts advanced across the failing boundary.
  - The resume/activate running window is not the first divergence because its fresh joint sample remains below 0.002 rad.
  - The first measured divergence is the paused bounded step of 20 physics steps, which advances the plant farther than the active controllers correct while paused.
conclusion: VALID diagnostic evidence localizes the unchanged transaction's joint-convergence failure to StepSimulation(20), not reset, resume/activate, or stale sampling.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-024/boundary-events.json (sha256 2bab6f76f94de2a9f60153ab60b1cf383e088dde8ac555d0830f7d5e89148680)
  - /tmp/so101-debug-mujoco-migration/exp-024/diagnostic.log (sha256 a95793ac6697e2551139d22f2888a29c52bb03831faa7070b4223e7f504747e2)
  - /tmp/so101-debug-mujoco-migration/exp-024/launch.log (sha256 e63be4502e75e7c5dee93b06eb0c5b7aff2078fd1492a63a7ff9992689fe44cc)
decision: KEEP the frozen transaction order and thresholds; test the package's canonical five-step default as the single variable.
next_experiment: EXP-025
```

## Experiment EXP-025

```yaml
experiment_id: EXP-025
status: INVALID
prior_experiment: EXP-024
hypothesis: The stale live-test override of 20 paused physics steps, rather than the canonical production default of five, causes the post-reset joint divergence.
prediction: With the same build, model, transaction order, controllers, thresholds, and diagnostic capture, changing only step_count from 20 to 5 produces a new reset epoch and fresh finite evidence while all six joints remain within 0.002 rad.
single_variable: step_count changes from 20 to 5; all other runtime inputs and assertions remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD d93bba347c2dbd5794c223a9e88f976286a736a8 plus the same eight dirty Task 10 paths and installed two-package build.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; exact lock/provenance pass.
  - Fresh task-owned ROS_DOMAIN_ID 107 and session exp025-step5-domain107; no MoveIt, GUI, workflow motion, or hardware.
success_criteria:
  - The transaction returns a receipt with reset_epoch incremented exactly once and fresh finite atomic evidence.
  - Every fresh joint position is within 0.002 rad of zero after StepSimulation(5), controllers are active, and cleanup leaves domain 107 empty.
failure_criteria:
  - Fresh post-step evidence arrives but any joint exceeds 0.002 rad, or the unchanged transaction fails another typed physical postcondition.
invalid_criteria:
  - Missing boundary record, stale build/prefix, domain contamination, source-order mismatch, background executor failure, or incomplete task-owned cleanup.
provenance:
  source_commit: d93bba347c2dbd5794c223a9e88f976286a736a8 plus preserved eight Task 10 paths
  dependency_overlay: /data/work/ws_mujoco_ros2_control_003/install
  project_install: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 107
  gz_partition: NONE
  evidence_path: /tmp/so101-debug-mujoco-migration/exp-025/
commands:
  - command: Fresh headless stack plus /tmp/so101-debug-mujoco-migration/exp-025/joint_boundary_diagnostic.py
    exit_code: 0 (diagnostic completed; recorded reset outcome was failure)
observed:
  - After activation and before StepSimulation(5), the fresh joint maximum absolute error was 0.0003906908945067322 rad.
  - After StepSimulation(5), joint and evidence callback counts advanced, reset_epoch advanced from 0 to 1, and the fresh joint maximum absolute error was 0.002323864095551104 rad; joint 3 exceeded the frozen 0.002 rad gate.
  - The post-step object position was [0.27000180200395496, -0.00000000504245058, 0.07988525679531384] m and all recorded joint/object values were finite.
  - No later atomic evidence arrived while paused; the client exhausted the original deadline retrying typed EvidenceStale and returned ResetFailed.
  - Controllers remained active. The task-owned pane 4117905 and child stack were stopped/reaped, domain 107 was empty after cleanup, and unrelated tmux sessions remained.
inferred:
  - Reducing the step count materially reduces the joint divergence but does not satisfy the unchanged 0.002 rad hard gate, so the five-step hypothesis is disproven.
  - The lack of a post-step paused evidence publication is an independent evidence-authority boundary; further step-count tuning would conflate variables and guess at physics.
conclusion: INVALID for Task 10 qualification: one joint remains 0.000323864095551104 rad outside tolerance and the original deadline ends with typed EvidenceStale.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-025/boundary-events.json (sha256 80e8a2c4ef148d22a07a947a07179867385cf9116e6de8ac5889e13697222c00)
  - /tmp/so101-debug-mujoco-migration/exp-025/diagnostic.log (sha256 5208b93c569fc5bfbde96fb795da665e28970ce83c8a70e1205a6e9dbd5ba158)
  - /tmp/so101-debug-mujoco-migration/exp-025/launch.log (sha256 7ca273ea1369f804b25fe591051023c62801d7e9f003aba51200a767f82b656d)
decision: STOP; do not tune step count, tolerance, deadline, transaction order, or pause inference without a newly approved evidence-layer hypothesis.
next_experiment: NONE
```

## Checkpoint CP-010

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-007
current_hypothesis: The deterministic independent scene is ready for the pinned mujoco_ros2_control system and controller wiring.
working_tree_status: Clean at Task 7 implementation commit 583ef2fdaf1053cd5a66b90b8c56f7decb14f4b7; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent scene compiles with a fixed table, rigid free-joint cup, stable names, lights/camera, inherited home keyframe, and task_start keyframe.
  - Structural tests reject equality, weld, adhesion, mocap following, hidden cup actuators, and production object qpos/qvel write paths.
  - EXP-007 is VALID: ten simulated seconds remained finite; 2-to-10-second cup displacement was 4.4468415042278435e-06 m, final-two-second envelope was 9.676037340306193e-06 m, and net speed was 2.380545878240552e-06 m/s.
  - Passive cup damping 1.0 and all friction/damping values are explicitly UNCALIBRATED MuJoCo inputs, not migrated Gazebo/Bullet values; instantaneous solver qvel remains reported and cannot prove later atomic twist success.
  - Package-level colcon test passed 74 tests before the final provenance test addition; the final focused scene/provenance set passed 8 tests, and Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - Final-frame qvel alone is not a reliable stationary-pose metric for the contact solver; position displacement, sampled envelope, and net finite-difference speed remain required together.
  - Passive damping 0.01 and 0.1 did not satisfy the full predeclared stationarity gate.
open_risks:
  - No ROS graph, controller manager, or atomic support-plugin publication has run against the task scene.
next_command: Start Task 8 RED tests for pinned mujoco_ros2_control, controllers, and minimal launch.
```

## Checkpoint CP-011

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-008
current_hypothesis: The live atomic evidence stream can be consumed by a backend-specific MuJoCo observer with strict freshness and ordering enforcement.
working_tree_status: Clean at Task 8 implementation commit ad8f87717aa092eb023d0bc9090a06f64134abdd; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE; Task 8 tmux and PIDs 3774884, 3774929, 3774930, 3774931, 3774932, and 3774933 were stopped and verified absent.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - The minimal launch defaults to start_simulation=false, run_mode=dry_run, headless=true, a 30-second readiness timeout, and a newly generated simulation session id.
  - EXP-008 is VALID in isolated ROS_DOMAIN_ID 81: all three controllers were active, /joint_states exposed joints 1 through 6, /clock published, and atomic evidence carried the exact session id, finite object pose/twist, table contact, and truncated=false.
  - The copied URDF's corrupted shell-expanded model path was replaced by launch-resolved package-local scene/headless tokens; installed launch/config/scene assets were used at runtime.
  - Package-level colcon test passed 80 tests with zero errors, failures, or skips; Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - A plain resolved URDF cannot retain an unexpanded $(find ...) expression; launch-time explicit package-share substitution is required.
  - Reusing a non-symlink ament Python build artifact blocks --symlink-install; the exact stale Task-owned directory was moved recoverably under the evidence root before rebuilding.
open_risks:
  - With no commanded trajectory, the live robot settled away from zero under gravity (joint 2 approximately 1.094 rad); wiring success is not action or physical success and controller/actuator tuning remains unproven.
  - Atomic evidence freshness, session/reset ordering, and reset receipt correlation are not yet enforced by a Python observer/reset adapter.
next_command: Start Task 9 RED tests for the MuJoCo observer.
```

## Experiment EXP-002

```yaml
experiment_id: EXP-002
status: INVALID
hypothesis: The initial independent scene remains finite and stationary for ten simulated seconds.
independent_variable: First uncalibrated MuJoCo table/cup contact inputs in the dirty Task 7 scene.
controlled_variables: Headless MuJoCo vendor library; timestep 0.002 s; no ROS graph; no controller launch; no hardware; no object state writes.
acceptance_criteria: Finite state through ten seconds; fixed table; cup displacement and final translational speed each no greater than 1.0e-05 in their declared units.
evidence_path: Console result associated with CP-009; RED artifact /tmp/so101-debug-mujoco-migration/task7-red.txt records the preceding missing-scene boundary.
owned_processes: NONE
result: INVALID because cup displacement was 4.034323607231733e-05 m and final translational speed was 0.009015012052262135 m/s; additionally, PLANNED was not recorded before execution.
next_command: NONE
```

## Experiment EXP-003

```yaml
experiment_id: EXP-003
status: INVALID
hypothesis: The failed cup-speed gate is explained by a vertical contact/integration residual rather than horizontal drift or an incorrect qvel slice.
independent_variable: Read-only capture of the complete free-joint cup position and velocity components at settle and at ten seconds using the existing scene and timestep.
controlled_variables: Exact dirty Task 7 scene; timestep 0.002 s; same initial keyframe/default state; MuJoCo vendor library; no ROS graph; no controller launch; no hardware; no source-state mutation after start.
acceptance_criteria: State layout is 1 time + 13 qpos + 12 qvel; cup quaternion remains finite and normalized; reported cup translational components identify whether the residual is vertical; cup horizontal displacement remains no greater than 1.0e-05 m.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-003-contact-residual.json
owned_processes: NONE
result: INVALID. State layout was correct and quaternion norm was 1.0, but the residual was not vertical: horizontal displacement was 4.0322194457956205e-05 m and final linear velocity was [-0.007257727062271137, 0.005347353961549931, -4.0568484134831707e-05] m/s. Evidence SHA-256 is 09a041b52afd0cc18eeb66572c1aa15f17199c40b4c40db7057ab29e85b3a339.
next_command: NONE
```

## Experiment EXP-004

```yaml
experiment_id: EXP-004
status: INVALID
hypothesis: A small explicitly uncalibrated passive damping value on the cup free joint allows contact motion to decay below the unchanged stationary gate by ten seconds without constraining or actuating the object.
independent_variable: cup_free_joint_damping = 0.01 N-s per generalized velocity unit.
controlled_variables: Exact EXP-003 scene and checker; unchanged timestep, table/cup friction, initial pose, 10-second duration, and 1.0e-05 displacement/speed limits; no equality, weld, adhesion, mocap, actuator, teleport, or object state write.
acceptance_criteria: All structural gates pass; finite state; cup displacement from 2 to 10 seconds no greater than 1.0e-05 m; final translational speed no greater than 1.0e-05 m/s.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-004-passive-damping.json
owned_processes: NONE
result: INVALID. Structural tests passed, but displacement was 1.5165012719267708e-05 m and final speed was 0.0004656655362538531 m/s. Evidence SHA-256 is b4959e6270cbcd41b7fae792d56391d0009cbfdcbc9d1d4f4bf1bad72df98a77.
next_command: NONE
```

## Experiment EXP-005

```yaml
experiment_id: EXP-005
status: INVALID
hypothesis: Increasing only the explicitly uncalibrated passive cup free-joint damping to 0.1 allows contact motion to decay below the unchanged stationary gate by ten seconds.
independent_variable: cup_free_joint_damping = 0.1 N-s per generalized velocity unit.
controlled_variables: Exact EXP-004 scene and checker; unchanged timestep, friction, pose, duration, and 1.0e-05 limits; no hidden constraint, actuator, teleport, or object state write.
acceptance_criteria: Structural gates pass; finite state; displacement from 2 to 10 seconds and final translational speed each no greater than 1.0e-05 in declared units.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-005-passive-damping.json
owned_processes: NONE
result: INVALID. Position displacement passed at 1.8224771852428455e-06 m, but instantaneous final translational qvel was 0.0006198185333119207 m/s. Evidence SHA-256 is 9be96d419449c8c95c1e435de34f70f4df90a8578c096f2da6d2cdb0294d38fe.
next_command: NONE
```

## Experiment EXP-006

```yaml
experiment_id: EXP-006
status: INVALID
hypothesis: The nonzero final cup qvel is a contact-solver residual that does not represent macroscopic cup motion over the final two seconds.
independent_variable: Add read-only 100 Hz position sampling over simulated seconds 8 through 10 and compare pose envelope/net finite-difference speed with final qvel.
controlled_variables: Exact EXP-005 model and all physical parameters; checker remains read-only; existing pass/fail thresholds remain unchanged during diagnosis.
acceptance_criteria: Finite sampled states; final-two-second translation envelope and net finite-difference speed are reported; evidence establishes whether they are below 1.0e-05 m and 1.0e-05 m/s while instantaneous qvel is not.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-006-stationarity-metrics.json
owned_processes: NONE
result: INVALID. Net final-two-second speed was 2.3202913980782535e-06 m/s, but the 201-sample translation envelope was 1.920915022571309e-05 m, above the unchanged 1.0e-05 m gate. Evidence SHA-256 is 36d9396f6abba8c865e66b1fd7b8d7f64c537ff25ffe51e3af7f6597ebb25d5b.
next_command: NONE
```

## Experiment EXP-007

```yaml
experiment_id: EXP-007
status: VALID
hypothesis: Increasing only passive cup free-joint damping from 0.1 to 1.0 suppresses the measured final-two-second pose envelope below 1.0e-05 m.
independent_variable: cup_free_joint_damping = 1.0 N-s per generalized velocity unit.
controlled_variables: Exact EXP-006 scene/checker and all other physics inputs; unchanged structural and stationarity limits; no hidden grasp mechanism or object state write.
acceptance_criteria: Structural gates pass; finite state; 2-to-10-second displacement, final-two-second translation envelope, and final-two-second net speed are all no greater than 1.0e-05 in declared units.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-007-passive-damping.json
owned_processes: NONE
result: VALID. Structural gates passed; 2-to-10-second displacement was 4.4468415042278435e-06 m, final-two-second envelope was 9.676037340306193e-06 m, and net speed was 2.380545878240552e-06 m/s. Instantaneous qvel remains reported as a solver residual and is not used to claim later atomic twist success. Evidence SHA-256 is feaf3cd7895fcace7bc5dfad5765e0bd7f007859bfe02cbc901584a031a5aee4.
next_command: Run the full Task 7 package, Ruff, isolation, and protected-tree gates.
```

## Experiment EXP-008

```yaml
experiment_id: EXP-008
status: VALID
hypothesis: The pinned apt MuJoCo system, independent controller configuration, and atomic evidence plugin launch together in an isolated ROS domain and expose the required Task 8 runtime interfaces.
independent_variable: Launch Task 8 with start_simulation=true, headless=true, run_mode=dry_run, simulation_session_id=task8-20260810-81, and ROS_DOMAIN_ID=81.
controlled_variables: Installed worktree overlay; apt mujoco_ros2_control 0.0.3; independent package assets; no MoveIt/workflow; no hardware; no commands; unrelated domains, sessions, and processes preserved.
acceptance_criteria: Controller manager lists active joint_state_broadcaster, arm_controller, and gripper_controller; /joint_states and /clock each publish; atomic evidence publishes the exact session id with finite object state; launch exits cleanly when only the recorded task-owned session is stopped.
evidence_path: /tmp/so101-debug-mujoco-migration/task8-runtime/
owned_processes: tmux session so101-mujoco-task8; launch PID 3774884; robot_state_publisher PID 3774929; ros2_control_node PID 3774930; one-shot spawner PIDs 3774931, 3774932, and 3774933. All stopped and verified absent.
result: VALID. All three controllers were active; /joint_states contained joints 1 through 6; /clock published; atomic evidence session id was task8-20260810-81 with finite cup pose/twist, table contact, and truncated=false. Domain 81 contained no nodes after stopping the owned session. Evidence hashes: launch 07470fb7..., controllers 7a77a1a3..., joint states 40200621..., clock af647d99..., atomic evidence 8c68190a..., process tree d21a697e..., empty post-stop nodes e3b0c442....
next_command: Run complete Task 8 package tests and isolation gates, then create the scoped implementation commit.
```

## Experiment EXP-009

```yaml
experiment_id: EXP-009
status: INVALID
hypothesis: MujocoWorldObserver consumes consecutive real atomic plugin messages in an isolated domain while enforcing its configured session and freshness contract.
independent_variable: Run test_observer_live_contract.py against a task-owned headless launch with session task9-20260810-82 in ROS_DOMAIN_ID 82.
controlled_variables: Task 8 launch/config/model; no commands, MoveIt, workflow, or hardware; unrelated sessions/processes preserved; observer max_age_s=0.5.
acceptance_criteria: Live pytest receives two consecutive accepted immutable evidence values with exact session id, increasing publisher sequence, nondecreasing step, cup identity, complete contact arrays, and truncated=false; only recorded task-owned processes are stopped afterward.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-runtime/
owned_processes: tmux session so101-mujoco-task9; launch PID 3790065; robot_state_publisher PID 3790107; ros2_control_node PID 3790108; all stopped and verified absent.
result: INVALID. The isolated plugin launched and published its topic, but test_observer_live_contract received no accepted snapshot in 10 seconds (first=None, second=None). Live test evidence SHA-256 is e106c67b5f00ab7190a1dd02d673712174172f98ba22fd01ffc598d931f163a2; launch log 63ca0175...; process tree 78a7530f.... No diagnostic run was performed after the critical gate failure.
next_command: NONE
```

## Checkpoint CP-012

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-008
current_hypothesis: The observer unit contract is correct, but the first live subscriber run either receives no callback or rejects every callback before storing latest evidence.
working_tree_status: Dirty Task 9 observer, unit/live tests, package dependency, and this checkpoint are intentionally preserved; no files are staged.
owned_processes: NONE; Task 9 tmux and PIDs 3790065, 3790107, and 3790108 were stopped and verified absent.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - Synthetic observer RED then GREEN passed 7 unit tests for conversion, immutable output, wrong-session/truncated/missing-side rejection, ordering, freshness, and rejection diagnostics.
  - Ruff passed and both independent packages built successfully before the isolated live test.
  - EXP-009 is INVALID because no live snapshot was accepted within 10 seconds; the test provides no evidence yet distinguishing discovery/QoS from conversion rejection.
disproven_routes:
  - Unit conversion and ordering tests alone are insufficient to claim the observer consumes real plugin output.
open_risks:
  - The live callback may not execute, or every real message may violate a conversion/ordering invariant; exact cause is intentionally unresolved after the critical gate failure.
next_command: NONE
```

## Checkpoint CP-013

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-012
current_hypothesis: The proven observer stream can be correlated transactionally with pause, named reset, and exact step services.
working_tree_status: Clean at Task 9 implementation commit 263818aabc5a6be09db8baaa137eb18668081d42; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE; all Task 9 diagnostic/repeat tmux sessions and recorded descendants were stopped and verified absent.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - MujocoWorldObserver converts one atomic ROS message into immutable backend-neutral evidence and rejects wrong sessions, truncation, missing arrays, stale receipts, publisher-sequence regression, step regression, same-step unpaused evidence, and reset-epoch skips.
  - Callback rejection diagnostics expose count and last reason without replacing the latest accepted snapshot.
  - EXP-012 is VALID: five of five fresh launch/domain/subscriber runs passed with exact sessions, increasing sequences, nondecreasing steps, complete contact arrays, clean owned-PID shutdown, and empty post-stop domains.
  - Package colcon reported 87 passed and one explicitly opt-in live skip; the skipped live case was separately executed successfully five times. Ruff, isolation, and protected-tree gates passed.
disproven_routes:
  - The first EXP-009 timeout did not represent a persistent observer defect; five valid fresh runs could not reproduce it.
  - Shell nounset is incompatible with the ROS setup scripts used by the repeat harness, and daemon-backed node lists are not authoritative for post-stop isolation checks.
open_risks:
  - Pause/reset/step service responses are not yet correlated to observer epoch/step evidence or exposed as ResetReceipt.
next_command: Start Task 10 RED tests for transactional pause/reset/step.
```

## Experiment EXP-010

```yaml
experiment_id: EXP-010
status: INVALID
hypothesis: Real plugin callbacks are arriving, but every message is rejected by one observable observer invariant before latest evidence is stored.
independent_variable: Add rejection count/last-reason to the unchanged live test failure and rerun once against session task9-diag-20260810-83 in ROS_DOMAIN_ID 83.
controlled_variables: Exact Task 9 observer logic and Task 8 launch/model/plugin; no command, MoveIt, workflow, hardware, threshold change, or QoS change; task-owned tmux only.
acceptance_criteria: Failure output distinguishes zero callbacks (rejected_count=0) from systematic rejection (rejected_count>0 with exact reason), enabling one root-cause boundary without changing acceptance behavior.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-diagnostic/
owned_processes: tmux session so101-mujoco-task9-diag and descendants, to be recorded and stopped.
result: INVALID because the hypothesized systematic rejection did not reproduce: the unchanged observer live test passed in 0.42 seconds with no rejection failure. Evidence SHA-256 is 791acbb2840ecff621592488f8e65512e312896e3865560d4000495c22ef5d13; all task-owned processes were stopped.
next_command: NONE
```

## Experiment EXP-011

```yaml
experiment_id: EXP-011
status: INVALID
hypothesis: The live observer contract is repeatable across five fresh simulator/subscriber discovery boundaries and the EXP-009 timeout was a nonpersistent first-run anomaly.
independent_variable: Five fresh launches and live pytest processes with unique domains 84 through 88 and exact session ids task9-repeat-1 through task9-repeat-5.
controlled_variables: Exact observer, live test, Task 8 launch/model/plugin, 10-second timeout, no commands/MoveIt/workflow/hardware; each task-owned tmux and descendants stopped before the next run.
acceptance_criteria: Five of five fresh runs pass; each post-stop domain is empty; no task-owned PID remains; rejection diagnostics remain available on any failure.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-repeat/
owned_processes: Per-run tmux sessions so101-mujoco-task9-r1 through r5 and their recorded descendants.
result: INVALID before observer execution. Harness nounset caused ROS setup to omit the installed so101_mujoco_support Python package, producing collection ModuleNotFoundError; daemon-backed node listing then reported stale names although all recorded PIDs were absent and --no-daemon showed domain 84 empty.
next_command: NONE
```

## Experiment EXP-012

```yaml
experiment_id: EXP-012
status: VALID
hypothesis: The live observer contract passes across five fresh simulator/subscriber discovery boundaries when the ROS environment and cleanup probes are valid.
independent_variable: Five fresh launches/live pytest processes with unique domains 89 through 93 and session ids task9-repeat-valid-1 through task9-repeat-valid-5.
controlled_variables: Exact observer/live test/Task 8 stack; no shell nounset; cleanup uses recorded PIDs and ros2 node list --no-daemon; no product source changes, commands, MoveIt, workflow, or hardware.
acceptance_criteria: Five of five live tests pass; each recorded launch PID disappears; each domain is empty via --no-daemon after stop; no unrelated session/process is changed.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-repeat-valid/
owned_processes: Per-run tmux sessions so101-mujoco-task9-v1 through v5 and recorded descendants.
result: VALID. Five of five fresh live observer tests passed in domains 89 through 93; every recorded launch/child PID disappeared and every post-stop --no-daemon node list was empty. Live-test SHA-256 values are 3a650440..., c9bcb144..., 4237eb8d..., 718af798..., and 261e0cc6....
next_command: Run full package, Ruff, isolation, and protected-tree gates and create the scoped Task 9 commit.
```

## Experiment EXP-013

```yaml
experiment_id: EXP-013
status: INVALID
hypothesis: Two consecutive transactional task_start resets produce sequential atomic epochs, converged zero joint state, and converged cup pose while remaining paused.
independent_variable: Run test_reset_live_contract.py once against session task10-reset-20260810-94 in isolated ROS_DOMAIN_ID 94; the test performs exactly two reset transactions with 20 bounded physics steps each.
controlled_variables: Pinned apt 0.0.3 pause/reset/step services; strict arm/gripper controller switching; observer max age 0.5 s; joint tolerance 0.002 rad; object tolerance 0.003 m; no MoveIt/workflow/hardware or object state writes.
acceptance_criteria: Live pytest passes; receipts correlate old->new epochs twice; final epoch equals second receipt; simulation_step>0; six joints converge to zero within 0.002 rad; cup converges to task_start within 0.003 m; failure leaves paused; owned processes stop cleanly.
evidence_path: /tmp/so101-debug-mujoco-migration/task10-runtime/
owned_processes: tmux session so101-mujoco-task10; launch PID 3814980 and recorded descendants; all stopped and verified absent.
result: INVALID on the first transaction. Pause succeeded, then strict controller deactivation timed out after 5 seconds because the paused simulation clock did not advance the controller-manager switch cycle. Reset was not called. Failure handling left the world paused. Live-test SHA-256 is 9a2ed86f8728954af9a2fbb72a725c09fc8553cd1ff087c671ac87fc5b8b45da; launch ac60e8fc...; process tree 8ab4066d....
next_command: NONE
```

## Checkpoint CP-014

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-012
current_hypothesis: A controller lifecycle switch requested after pausing cannot complete until an explicit paused simulation step advances the controller-manager update loop.
working_tree_status: Dirty Task 10 client/reset/unit/live tests, package dependencies, and this checkpoint are intentionally preserved; no files are staged.
owned_processes: NONE; Task 10 tmux, launch PID 3814980, and recorded descendants were stopped and verified absent; domain 94 is empty via --no-daemon.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - Transaction unit RED/GREEN passes 8 tests for ordering, service/controller failure, timeout, epoch mismatch, joint convergence, sequential receipts, and failure-paused behavior.
  - The concrete client uses only pinned apt 0.0.3 pause/reset/step services plus standard Jazzy controller-manager switch/list and joint states.
  - EXP-013 is INVALID at the exact first bad boundary: pause succeeded and strict deactivate timed out before reset; no reset receipt or physical convergence was claimed.
disproven_routes:
  - A synchronous strict controller switch immediately after pause cannot complete without advancing the paused controller-manager cycle.
open_risks:
  - The correct atomic ordering for pause, lifecycle switch, and explicit stepping must be proven without allowing controllers to snap the reset state or weakening failure-paused behavior.
next_command: NONE
```

## Experiment EXP-014

```yaml
experiment_id: EXP-014
status: INVALID
hypothesis: A pending strict controller switch completes deterministically if exactly one pinned StepSimulation step advances the paused controller-manager cycle, allowing the original pause->deactivate->reset->activate->bounded-step transaction to remain intact.
independent_variable: Modify only MujocoRosClient.switch_controllers to issue one StepSimulation{steps:1} when the strict switch future remains pending after initial spinning.
controlled_variables: Exact Task 10 reset coordinator, two-cycle live test, session/task_start keyframe, 20 bounded post-reset steps, tolerances, controller list, model, domain isolation, failure-paused behavior, no MoveIt/workflow/hardware or state writes.
acceptance_criteria: Eight unit transaction tests remain green; two live resets pass with sequential epochs, zero-joint convergence, cup pose convergence, world paused; switch and one-step responses both succeed; owned cleanup is complete.
evidence_path: /tmp/so101-debug-mujoco-migration/task10-runtime-fix1/
owned_processes: tmux session so101-mujoco-task10-fix1 and descendants, to be recorded and stopped.
result: INVALID at the same first transaction boundary. After pause, strict deactivate remained pending; concurrently issuing exactly one StepSimulation step did not complete the switch within 5 seconds. Reset was not called and failure handling left the world paused. Evidence SHA-256: live test be50f86a..., launch 046d2ec4..., process tree 9a0fec3c....
next_command: NONE
```

## Checkpoint CP-015

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-012
current_hypothesis: Controller-manager lifecycle switching while the controller manager uses paused ROS time requires a different proven coordination boundary than one concurrent physics step.
working_tree_status: Dirty Task 10 client/reset/unit/live work and ledger are intentionally preserved; no files are staged.
owned_processes: NONE; Task 10 fix1 tmux, launch PID 3818423, and recorded descendants were stopped and verified absent; domain 95 is empty via --no-daemon.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - Unit, Ruff, and build gates remained green after the one-step pending-switch handshake.
  - EXP-014 is INVALID because strict deactivate still timed out before reset; no receipt, epoch advance, joint convergence, or object convergence was claimed.
disproven_routes:
  - One concurrent paused StepSimulation step is insufficient to complete the strict controller switch in this controller-manager/sim-time configuration.
open_risks:
  - Whether a bounded multi-step handshake, temporary controller-manager wall-time trigger, or a different transaction ordering is compatible with the approved pause-first interface remains unproven.
next_command: NONE
```

## Experiment EXP-015

```yaml
experiment_id: EXP-015
status: INVALID
hypothesis: The strict switch transition succeeds after pause, but the Python switch service future is not a reliable completion signal; polling authoritative list_controllers states can prove completion without extra physics steps.
independent_variable: Replace the pending-future/one-step handshake with bounded polling for exact inactive/active states after sending the same strict switch request.
controlled_variables: Pause-first transaction, strict switch request, reset/step services, controller names, two-cycle live test, tolerances, model, no commands/MoveIt/workflow/hardware or object writes.
acceptance_criteria: Unit/Ruff/build green; launch log and list_controllers agree on each transition; two live resets yield sequential receipts and joint/object convergence; no extra pre-reset physics step is injected; cleanup complete.
evidence_path: /tmp/so101-debug-mujoco-migration/task10-runtime-fix2/
owned_processes: tmux session so101-mujoco-task10-fix2 and descendants, to be recorded and stopped.
result: INVALID before any reset transaction. The live test accepted no atomic evidence during its 10-second readiness loop, reproducing the intermittent EXP-009 discovery/callback boundary. No pause, switch, reset, or step was requested, so state-polling switch completion remains untested. Evidence SHA-256: live test dc18c6c8..., launch 43a881d8..., process tree a4fa64fe....
next_command: NONE
```

## Checkpoint CP-016

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-012
current_hypothesis: Intermittent late subscriber discovery or callback delivery can prevent the reset live test from receiving its first best-effort SensorDataQoS atomic sample even while the publisher topic is discoverable.
working_tree_status: Dirty Task 10 work and ledger are intentionally preserved; no files are staged.
owned_processes: NONE; Task 10 fix2 tmux, launch PID 3822243, and recorded descendants were stopped and verified absent; domain 96 is empty via --no-daemon.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - EXP-014 log proves strict deactivate actually completed server-side in about 108 ms despite the unresolved Python service future, motivating exact controller-state polling.
  - Unit/Ruff/build gates remained green after replacing future completion with authoritative controller state polling.
  - EXP-015 is INVALID before reset because no observer sample was accepted in 10 seconds; no switch/reset behavior from the fix2 client was exercised or claimed.
disproven_routes:
  - Topic discovery alone is insufficient readiness proof for a best-effort atomic subscriber; an accepted observer snapshot is required.
open_risks:
  - The intermittent first-sample failure requires a deterministic subscription/readiness boundary before reset transactions can be qualified.
  - The state-polling switch implementation still lacks live reset evidence because EXP-015 never reached it.
next_command: NONE
```

## Experiment EXP-016

```yaml
experiment_id: EXP-016
status: INVALID
hypothesis: The intermittent readiness failure can be localized by distinguishing matched publisher count, raw callback count, and conversion rejection count without changing QoS or timeout.
independent_variable: Add observer callback_count diagnostics and include callback_count, rejected_count, last_rejection, and node.count_publishers in reset-live readiness failure.
controlled_variables: Exact Task 10 state-polling client/reset transaction, SensorDataQoS, 10-second readiness, two reset cycles, model/config/tolerances, isolated fresh domain, no command/MoveIt/workflow/hardware.
acceptance_criteria: Unit diagnostics test RED->GREEN; one live run either passes both resets or fails with publisher/callback/rejection counts that identify the first boundary; owned cleanup complete.
evidence_path: /tmp/so101-debug-mujoco-migration/task10-runtime-diag/
owned_processes: tmux session so101-mujoco-task10-diag and descendants, to be recorded and stopped.
result: INVALID before reset. At the 10-second readiness deadline the node graph reported exactly one publisher, while observer callback_count=0, rejected_count=0, and last_rejection was empty. No pause/switch/reset/step was called. Evidence SHA-256: live test 8be08bc3..., launch 3fc75a64..., process tree b00f9379....
next_command: NONE
```

## Checkpoint CP-017

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-012
current_hypothesis: The intermittent readiness failure occurs below observer conversion: graph discovery sees one publisher but the best-effort subscription receives zero callbacks, implicating endpoint QoS/data publication or DDS delivery.
working_tree_status: Dirty Task 10 work and ledger are intentionally preserved; no files are staged.
owned_processes: NONE; Task 10 diagnostic tmux, launch PID 3826113, and recorded descendants were stopped and verified absent; domain 97 is empty via --no-daemon.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - Observer callback_count diagnostics passed RED->GREEN with all 15 observer/reset unit tests, Ruff, and build gates green.
  - EXP-016 observed publishers=1, callbacks=0, rejected=0 at timeout, excluding message conversion/session/order rejection as the first boundary.
  - No reset transaction was attempted, so the authoritative controller-state polling implementation remains live-unverified.
disproven_routes:
  - Extending conversion diagnostics cannot explain the failure because no callback reached conversion.
open_risks:
  - Publisher offered QoS and actual publication continuity must be captured together with subscriber requested QoS in the next controlled run.
  - A background simulator thread stack trace appeared in EXP-015 and may correlate with publication stopping, but causality is unproven.
next_command: NONE
```

## Experiment EXP-017

```yaml
experiment_id: EXP-017
status: INVALID
hypothesis: MujocoRosClient's continuously ready 100 Hz joint-state callback starves the atomic evidence callback because progress invokes only one rclpy spin_once per iteration.
independent_variable: Add read-only joint_callback_count diagnostics; capture topic info --verbose and direct evidence --once before running the unchanged reset readiness loop.
controlled_variables: Exact SensorDataQoS on both subscriptions, 10-second timeout, state-polling reset client, simulator/config/session, no transaction requests before readiness, no MoveIt/workflow/hardware.
acceptance_criteria: Direct evidence echo proves publisher data exists; topic QoS is compatible; reset readiness failure or success reports joint/evidence callback counts sufficient to confirm or reject starvation.
evidence_path: /tmp/so101-debug-mujoco-migration/task10-callback-diag/
owned_processes: tmux session so101-mujoco-task10-callback-diag and descendants, to be recorded and stopped.
result: INVALID during the first reset transaction. Offered QoS was BEST_EFFORT/VOLATILE and direct evidence echo succeeded; reset readiness then passed. Pause and server-side strict deactivate began, but the client timed out waiting for list_controllers while the switch request was pending. Evidence SHA-256: live acaf8e81..., launch 184b7726..., QoS f034669d..., direct evidence 41aea283..., process tree 0ef91589....
next_command: NONE
```

## Checkpoint CP-018

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-012
current_hypothesis: Sharing one rclpy node between high-rate joint/evidence subscriptions and synchronous service futures causes response starvation; list_controllers also cannot run while the controller-manager switch callback remains pending in its callback group.
working_tree_status: Dirty Task 10 work and ledger are intentionally preserved; no files are staged.
owned_processes: NONE; Task 10 callback diagnostic tmux, launch PID 3829377, and recorded descendants were stopped and verified absent; domain 98 is empty via --no-daemon.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - The plugin publisher offers BEST_EFFORT/VOLATILE QoS and continuously published valid atomic data; direct evidence echo succeeded with exact session and finite state.
  - Reset readiness passed in EXP-017, excluding a persistent publisher/QoS incompatibility.
  - The first transaction failed when list_controllers response timed out during a pending strict switch; no reset was called.
disproven_routes:
  - Polling list_controllers from the same client while the switch service callback is pending cannot serve as the completion boundary.
  - Extending readiness timeout or changing evidence QoS is unsupported by EXP-017 because direct evidence and readiness both succeeded.
open_risks:
  - A dedicated service-only node/executor must prove switch service future completion without subscription starvation before the transaction can continue.
next_command: NONE
```

## Experiment EXP-018

```yaml
experiment_id: EXP-018
status: INVALID
hypothesis: Separating observer, joint-state, and service clients onto three rclpy nodes removes subscription starvation and allows strict switch futures/list verification to complete deterministically.
independent_variable: MujocoRosClient takes distinct service_node and joint_state_node; live test uses a third observer_node and explicitly advances observer/joint nodes only during evidence convergence.
controlled_variables: Same services, strict state-polling transaction, QoS, timeout, two task_start resets, tolerances, model/config/session, no commands/MoveIt/workflow/hardware.
acceptance_criteria: Node-separation behavior test RED->GREEN; all existing units/Ruff/build green; live readiness accepts evidence; two resets return sequential receipts with zero joints/cup convergence; cleanup complete.
evidence_path: /tmp/so101-debug-mujoco-migration/task10-runtime-node-isolation/
owned_processes: tmux session so101-mujoco-task10-node-isolation and descendants, to be recorded and stopped.
result: INVALID. Readiness passed, but the first strict deactivate request timed out before reset_world. The dedicated service node did not remove the failure. Server log reports `Switch controller timed out after 5 seconds!`; no reset receipt exists and the run cannot count. The exact owned session and descendants were stopped, and ROS_DOMAIN_ID 99 was empty afterward.
next_command: NONE
```

## Checkpoint CP-019

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-012
current_hypothesis: The controller-manager strict switch cannot complete while the MuJoCo simulation is paused; node-level response starvation is no longer sufficient to explain the server-side timeout.
working_tree_status: Dirty Task 10 implementation and ledger preserved exactly; no files staged. Paths: docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md, src/so101_mujoco_demo_py/package.xml, src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/observer.py, src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/client.py, src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py, src/so101_mujoco_demo_py/test/test_mujoco_observer.py, src/so101_mujoco_demo_py/test/test_mujoco_reset.py, src/so101_mujoco_demo_py/test/test_reset_live_contract.py.
owned_processes: NONE; task-owned tmux so101-mujoco-task10-node-isolation, pane 3838745, launch 3838818, and recorded descendants were stopped; ROS_DOMAIN_ID 99 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - Three-node unit contract is GREEN (16 passed, one opt-in live skip), and package colcon test executed 98 tests with 96 passed, zero failures, and two opt-in skips.
  - The colcon JUnit contains both real Ruff integration tests: the actual package gate passes and an injected F821 makes the copied real gate fail; Ruff 0.15.20 direct gate passes check and format --check.
  - EXP-018 readiness and ROS service provenance passed, but the first strict deactivate timed out before reset_world; controller-manager itself logged a five-second switch timeout.
disproven_routes:
  - Splitting observer, service, and joint subscriptions across three nodes is not sufficient to make the paused strict controller switch complete.
open_risks:
  - Transaction ordering pause-before-deactivate may prevent controller-manager from receiving update cycles required to finish switching; this is a hypothesis only and requires revised-plan/user direction before another runtime attempt.
  - Task 10 has no atomic commit because its mandatory live two-reset gate failed.
next_command: NONE
```

## Experiment EXP-019

```yaml
experiment_id: EXP-019
status: VALID
prior_experiment: EXP-018
hypothesis: With use_sim_time, pausing MuJoCo stops /clock and blocks the controller-manager control loop before its next update/manage_switch cycle, so strict deactivate succeeds while running but times out while paused.
prediction: A fresh running stack returns strict deactivate ok=true well below five seconds and controllers become inactive while evidence step/sequence advances; an otherwise identical fresh paused stack returns ok=false at approximately five seconds, controllers remain active, and evidence step/sequence does not advance during the switch.
single_variable: paused state at the instant of the identical strict deactivate request; A=false and B=true.
lifecycle: FULL_RESTART
preconditions:
  - Same HEAD 01ef1e11f7f3568ad326e2a8dc67f9f59dd17db8, installed overlay, launch arguments, controller set, strictness, activate_asap, and five-second request timeout for both arms.
  - A and B each use a fresh task-owned headless stack and unique ROS domain/session; no reset service, motion command, MoveIt workflow, GUI, or hardware action is permitted.
success_criteria:
  - A returns ok=true and list_controllers shows arm_controller and gripper_controller inactive.
  - B returns ok=false only after the server-side five-second timeout and list_controllers still shows both controllers active.
  - /clock or atomic evidence proves progression during A and halted step/sequence during B; overlay/PID/log provenance and exact cleanup are complete.
failure_criteria:
  - A does not succeed reliably, B succeeds, or controller/evidence facts do not show the predicted divergence; pause-blocking is then not confirmed.
invalid_criteria:
  - Stack readiness/provenance failure, non-identical switch request/configuration, reset invocation, cross-domain contamination, or incomplete owned-process cleanup.
provenance:
  source_commit: 01ef1e11f7f3568ad326e2a8dc67f9f59dd17db8 plus the eight preserved dirty Task 10 paths
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /opt/ros/jazzy/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: A=100, B=101
  gz_partition: NONE (MuJoCo only)
commands:
  - command: Fresh-stack A/B strict deactivate diagnostic; exact commands captured under /tmp/so101-debug-mujoco-migration/exp-019-ab/
    exit_code: 0
observed:
  - A running: strict deactivate returned ok=true in 0.003255506 s; arm_controller and gripper_controller changed active to inactive; evidence step 1007 to 1057, sequence 1008 to 1058, and clock 11.102 s to 11.610 s continued advancing.
  - B paused: set_pause(true) returned success in 0.000627837 s; identical strict deactivate returned ok=false in 5.001467380 s; both controllers remained active; evidence step/sequence stayed 957/957 and clock stayed 10.608 s through the switch.
  - B server log records Simulation paused followed by Switch controller timed out after 5 seconds; no reset service was called. Both exact task-owned stacks were stopped and domains 100/101 were empty afterward.
inferred:
  - CONFIRMED: pause blocks the simulation-clock-driven controller-manager update/manage_switch completion point in this 0.0.3 integration.
conclusion: A succeeded and B timed out under the frozen single-variable design, confirming pause-first is architecturally invalid for strict switching.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-019-ab/controller-switch-source.txt
  - /tmp/so101-debug-mujoco-migration/exp-019-ab/controller-loop-source.txt
  - /tmp/so101-debug-mujoco-migration/exp-019-ab/mujoco-003-relevant.txt
  - /tmp/so101-debug-mujoco-migration/exp-019-ab/hashes.txt
decision: KEEP
next_experiment: EXP-020
```

## Experiment EXP-020

```yaml
experiment_id: EXP-020
status: INVALID
prior_experiment: EXP-019
hypothesis: A bounded deactivate-running/pause/reset/resume-activate/re-pause sequence completes both controller switches while limiting uncontrolled physics to the two measured switch windows and preserving deterministic reset convergence.
prediction: A transaction-order contract first fails against pause-first; after the minimal ordering change, two live resets return sequential epochs, both controllers are active only after re-pause, final six-joint and cup states converge, and atomic evidence bounds pose/twist/step changes across each uncommanded window.
single_variable: Transaction ordering required by the confirmed pause/update dependency; service types, keyframe, step count, tolerances, model, controllers, and failure-paused guarantee remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-019 is VALID and proves strict switch requires a running simulation-clock control loop.
  - RED contract requires deactivate before first pause and requires resume/activate/re-pause before bounded stepping.
  - Production ordering may be exercised only in a fresh task-owned headless stack; no MoveIt command, reset teleport outside the pinned service, GUI, or hardware.
success_criteria:
  - RED fails only because production still uses pause-first; minimal GREEN passes all reset units and Ruff.
  - Live evidence records controller states, switch/resume timing, joint/object pose and twist around each bounded running window, sequential reset epochs, and final paused convergence for two cycles.
  - No uncontrolled-window displacement or velocity violates the existing reset tolerances; any physical-state ambiguity stops the experiment without commit.
failure_criteria:
  - Either switch times out, re-pause fails, epoch/state convergence fails, or atomic physical evidence cannot bound the running windows.
invalid_criteria:
  - Stale install, non-fresh stack/domain, missing pre/post atomic evidence, unrelated process contamination, or incomplete owned cleanup.
provenance:
  source_commit: 01ef1e11f7f3568ad326e2a8dc67f9f59dd17db8 plus preserved Task 10 dirty paths
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /opt/ros/jazzy/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 102
  gz_partition: NONE (MuJoCo only)
commands:
  - command: Transaction-order RED, minimal GREEN, then one fresh-stack two-cycle live reset contract with expanded atomic diagnostics.
    exit_code: 1
observed:
  - RED failed only on pause-first ordering; minimal ordering GREEN passed 16 focused tests with one opt-in live skip, Ruff 0.15.20, and the two-package build.
  - Live server completed deactivate, pause, task_start reset, resume, activate, re-pause, and bounded step without a switch timeout; activation completed before re-pause.
  - The client then rejected its cached atomic frame as 0.506 s old before calling progress, so no complete pre/post physical-event JSON was emitted and the run is invalid by its preregistered evidence criterion.
inferred:
  - The bounded ordering removes the confirmed switch deadlock, but the observer convergence loop must advance subscriptions before its first post-service snapshot.
conclusion: INVALID due missing complete atomic evidence, not a controller-switch product failure.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-020-reset-order/
decision: REPEAT only after a RED/GREEN progress-before-snapshot regression.
next_experiment: EXP-021
```

## Checkpoint CP-020

```yaml
checkpoint_id: CP-020
last_valid_experiment: EXP-019
current_hypothesis: Advancing observer and joint subscriptions once before the first post-service snapshot will preserve the strict 0.5 s freshness gate and expose the new reset epoch without changing physics or timeouts.
working_tree_status: The same eight Task 10 paths remain dirty and unstaged; no protected or unrelated path is modified.
owned_processes: NONE; so101-mujoco-exp020 pane 3952486, launch 3952540, and recorded descendants were stopped; ROS_DOMAIN_ID 102 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-019 confirmed pause-first blocks controller-manager switch completion.
  - EXP-020 server logs show the bounded running-window ordering completes both strict switches and reset/step services.
disproven_routes:
  - Reading the cached snapshot before advancing subscriptions is incompatible with a strict freshness boundary after a multi-service reset sequence.
open_risks:
  - Complete atomic pose/twist/joint evidence for both bounded windows is still missing; no production commit is allowed.
next_command: Add and run a RED unit contract requiring progress before the first post-service snapshot.
```

## Experiment EXP-021

```yaml
experiment_id: EXP-021
status: INVALID
prior_experiment: EXP-020
hypothesis: A single progress call before each convergence snapshot fixes only evidence delivery ordering; the bounded switch sequence will then produce complete two-cycle atomic physical evidence within unchanged tolerances.
prediction: A unit observer that becomes fresh only after progress fails before the fix and passes after it; a fresh domain 103 live run returns two sequential receipts and four bounded-window snapshots with converged object/joint state.
single_variable: progress-before-snapshot in the convergence loop; transaction ordering, freshness 0.5 s, timeouts, tolerances, model, services, and diagnostics remain frozen from EXP-020.
lifecycle: FULL_RESTART
preconditions:
  - RED/GREEN focused tests and Ruff pass before runtime.
  - Fresh task-owned domain 103/session and exact rebuilt overlay provenance; no reset outside the transaction and no motion/MoveIt/hardware.
success_criteria:
  - Two reset receipts have sequential epochs; four pause-window records contain finite atomic pose/twist and six joints within existing 0.003 m/0.002 rad reset tolerances.
  - Both controller switches succeed, final controllers are active, world remains paused, cleanup is exact, and package/Ruff/isolation gates pass.
failure_criteria:
  - Any stale/session/epoch/controller/joint/object failure, switch timeout, missing window evidence, or tolerance violation.
invalid_criteria:
  - Provenance/readiness contamination, incomplete evidence, or incomplete owned cleanup.
provenance:
  source_commit: 01ef1e11f7f3568ad326e2a8dc67f9f59dd17db8 plus preserved Task 10 dirty paths
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /opt/ros/jazzy/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 103
  gz_partition: NONE (MuJoCo only)
commands:
  - command: Focused RED/GREEN then unchanged expanded live reset contract.
    exit_code: 1
observed:
  - Progress-before-snapshot RED failed at the intended stale-read boundary; minimal GREEN passed 17 focused tests with one opt-in live skip, Ruff 0.15.20, and the two-package build.
  - Fresh live services again completed both strict switches, reset, pause transitions, and step, but one spin consumed only an old queued frame; snapshot remained exactly 0.500 s stale and aborted before complete event JSON.
inferred:
  - Typed EvidenceStale is transient during bounded convergence and must be retried within the existing deadline; all other evidence failures remain terminal.
conclusion: INVALID because complete physical evidence is still missing; the switch/order hypothesis remains supported by server logs.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-021-progress-first/
decision: REPEAT only after a typed-stale retry RED/GREEN.
next_experiment: EXP-022
```

## Checkpoint CP-021

```yaml
checkpoint_id: CP-021
last_valid_experiment: EXP-019
current_hypothesis: Retrying only typed EvidenceStale inside the existing convergence deadline will drain queued frames without weakening freshness or physical assertions.
working_tree_status: The same eight Task 10 paths remain dirty and unstaged; protected tree remains untouched.
owned_processes: NONE; so101-mujoco-exp021 pane 3958262, launch 3958319, and recorded descendants were stopped; ROS_DOMAIN_ID 103 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-019 confirms the pause/update switch dependency.
  - EXP-020 and EXP-021 independently show both switches and the bounded reset service sequence complete with the new ordering.
disproven_routes:
  - A single subscription spin does not guarantee the newest queued atomic frame is delivered.
open_risks:
  - Full physical-window evidence remains unavailable; no Task 10 commit is permitted.
next_command: Add a typed stale-then-fresh RED and implement bounded retry without changing max_age or timeout.
```

## Experiment EXP-022

```yaml
experiment_id: EXP-022
status: INVALID
prior_experiment: EXP-021
hypothesis: Bounded retry of only EvidenceStale drains queued messages and yields complete atomic evidence for the already-proven service ordering.
prediction: Stale-then-fresh unit RED fails before the fix and passes after it; fresh domain 104 yields two reset receipts and four finite physical-window records within unchanged tolerances.
single_variable: Catch and retry EvidenceStale inside the existing convergence deadline; no timeout, freshness, service ordering, model, tolerance, or diagnostic change.
lifecycle: FULL_RESTART
preconditions:
  - Focused RED/GREEN, Ruff, and rebuilt overlay pass before runtime.
  - Fresh task-owned domain 104/session; no MoveIt/motion/GUI/hardware and exact cleanup.
success_criteria:
  - Two sequential epochs, four pause-window atomic pose/twist/joint records, active controllers, final paused state, and existing tolerances all pass.
failure_criteria:
  - Any non-stale evidence error, deadline, switch, epoch, joint, pose, missing record, or finite-value failure.
invalid_criteria:
  - Provenance/readiness contamination, incomplete diagnostics, or incomplete cleanup.
provenance:
  source_commit: 01ef1e11f7f3568ad326e2a8dc67f9f59dd17db8 plus preserved Task 10 dirty paths
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /opt/ros/jazzy/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 104
  gz_partition: NONE (MuJoCo only)
commands:
  - command: Typed stale retry RED/GREEN and unchanged two-cycle live contract.
    exit_code: 1
observed:
  - Typed-stale RED failed at the intended boundary; minimal GREEN passed 18 focused tests with one opt-in live skip, Ruff 0.15.20, and the two-package build.
  - Fresh live services completed both strict switches, reset, pause transitions, and 20 steps, but no evidence with reset_epoch incremented; the unchanged 10 s deadline expired.
  - Pinned MuJoCo 0.0.3 reset_simulation_state saves and restores mj_data_->time, while the Task 4 plugin increments reset_epoch only when data->time decreases. The direct ResetWorld service therefore cannot produce the planned epoch transition.
inferred:
  - CONFIRMED architectural incompatibility: reset epoch has no observable authoritative trigger across the pinned direct service/plugin boundary.
conclusion: INVALID for Task 10 qualification; continuing with retry/executor changes cannot satisfy the atomic reset contract.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-022-stale-retry/
decision: ABANDON retry-based fixes and require architecture/spec resolution.
next_experiment: NONE
```

## Checkpoint CP-022

```yaml
checkpoint_id: CP-022
last_valid_experiment: EXP-019
current_hypothesis: NONE; direct 0.0.3 ResetWorld plus time-decrease-only plugin epoch detection is structurally incapable of satisfying the approved atomic reset epoch contract.
working_tree_status: Eight Task 10 paths remain dirty and unstaged: docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md; src/so101_mujoco_demo_py/package.xml; src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/observer.py; src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/client.py; src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py; src/so101_mujoco_demo_py/test/test_mujoco_observer.py; src/so101_mujoco_demo_py/test/test_mujoco_reset.py; src/so101_mujoco_demo_py/test/test_reset_live_contract.py.
owned_processes: NONE; so101-mujoco-exp022 pane 3963214, launch 3963281, and recorded descendants were stopped; ROS_DOMAIN_ID 104 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-019 proves pause blocks controller-manager switch completion; bounded running windows remove that switch deadlock.
  - Pinned 0.0.3 reset preserves simulation time, while the evidence plugin's only reset trigger is a time decrease; no epoch increment can result from the direct service.
  - Three resumed live attempts completed the reordered services but could not produce qualifying atomic epoch evidence; no physical-success or Task 10 completion claim is valid.
disproven_routes:
  - More executor separation, progress-before-read, typed-stale retry, or timeout changes cannot create an absent reset epoch source.
open_risks:
  - Spec/plan must choose an auditable reset epoch authority, such as a project-owned reset proxy/event integrated with the evidence publisher; inferring from pose jumps is not reliable for idempotent resets.
  - The bounded deactivate/resume/activate ordering has server evidence but lacks complete atomic pose/twist window qualification and remains uncommitted.
next_command: NONE
```

## Checkpoint CP-023

```yaml
checkpoint_id: CP-023
last_valid_experiment: EXP-019
current_hypothesis: NONE; CP-022's reset-epoch authority conflict remains unresolved.
working_tree_status: The exact same eight Task 10 paths remain dirty and unstaged; no source, spec, plan, or protected Gazebo path changed during this continuation.
owned_processes: NONE; ROS domains 100 through 104 remain empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no process or session was stopped.
confirmed_conclusions:
  - The authoritative spec and plan have not changed since commit 45c6efc and still do not define an epoch source compatible with ResetWorld preserving simulation time.
disproven_routes:
  - NONE beyond CP-022.
open_risks:
  - Choosing a reset proxy/event or another epoch authority is an architecture change requiring explicit spec/plan approval.
next_command: NONE
```
```
```
```
```
```
```

## Checkpoint CP-RUFF-001

```yaml
checkpoint_id: CP-RUFF-001
last_valid_experiment: EXP-001
current_hypothesis: The main migration can resume with every new-package Python change guarded by the executable Ruff gate.
working_tree_status: Ruff gate, behavior tests, fixed configuration, mechanical lint/format changes, and this checkpoint are pending one isolated commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - Ruff 0.15.20 and rules E4, E7, E9, F, and I are explicitly pinned; the gate executes both check and format --check over only the independent MuJoCo Python package targets.
  - Strict RED produced 2 failures because the executable gate and configuration were absent; behavior GREEN passed 2 of 2.
  - The first real audit covered 8 Python files and found 6 I001 import-order findings across 6 files; format check identified 4 files requiring formatting and 4 already formatted.
  - Mechanical repair applied 6 import-order fixes and formatted 4 files without intended behavior change.
  - The package-level colcon test executed 47 pytest cases including a real Ruff pass and a disposable-copy F821 rejection; test-result reported zero errors, failures, or skips.
  - Complete pre-fix evidence is ruff-before-{files,check,statistics,format}.txt under the evidence root with SHA-256 values 2610d669..., 40e62557..., 6df5bb43..., and f1eff9fb... respectively.
disproven_routes:
  - A configuration-only or grep-only lint declaration is insufficient; pytest executes the gate and proves both Ruff subcommands and scope.
open_risks:
  - Future environments must provide exactly Ruff 0.15.20 or the gate intentionally fails closed.
next_command: Run final package tests, real Ruff gate, isolation and protected-tree gates, then commit the isolated Ruff change and resume Task 5.
```

## Checkpoint CP-024

```yaml
checkpoint_id: CP-024
last_valid_experiment: EXP-019
current_hypothesis: The pinned reset hook overlay supplies the missing authoritative epoch event; the already-verified bounded transaction order can now satisfy the full atomic reset contract.
working_tree_status: The original eight Task 10 paths remain present and unstaged. Task 10A adds only the dependency lock, replayable patch/build/provenance tools, dependency contract test, and three support-plugin generation paths; no protected Gazebo path changed.
owned_processes: NONE; the overlay build and tests completed without leaving a task-owned process or tmux session.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated process or session was stopped.
confirmed_conclusions:
  - Official upstream tag 0.0.3 and commit 35ba8174b62d9560093614f981a3d4b978a96036 were fetched from https://github.com/ros-controls/mujoco_ros2_control into the isolated dependency workspace.
  - The exact zero-context minimal patch SHA-256 is 367cf5e3eab641412e234a3b1db86922b5573704932e950f98d9ca394056ea9f; the checkout diff with the same zero-context serialization has the same hash.
  - Upstream build and tests passed 114 tests with zero errors, failures, or skips. The three upstream packages resolve to /data/work/ws_mujoco_ros2_control_003/install and mujoco_vendor resolves to /opt/ros/jazzy.
  - Project clean-cache rebuild resolves the patched plugin header from the dependency overlay. Generation-focused GTest passes 6 tests and proves time decrease is not an epoch authority and multiple generation increments are not collapsed.
disproven_routes:
  - A previously configured project CMake cache retained the apt include path despite correct shell source order; reset qualification requires clean reconfiguration when changing provider prefix.
open_risks:
  - The upstream hook's live exactly-once behavior and the complete two-cycle physical-window contract remain unqualified until EXP-023.
next_command: Complete Task 10A gates and dependency-hook commit, then preregister EXP-023 before launching a fresh isolated stack.
```

## Experiment EXP-023

```yaml
experiment_id: EXP-023
status: INVALID
prior_experiment: EXP-022
hypothesis: The pinned reset-qualified 0.0.3 hook makes each successful central ResetWorld observable exactly once, allowing the already-verified bounded transaction order to produce two complete deterministic reset receipts and atomic physical-window evidence.
prediction: Two task_start transactions on one fresh stack produce epochs N->N+1 and N+1->N+2; exactly four pause:true events carry finite atomic object pose/twist and six joint positions within 0.003 m and 0.002 rad; controllers are active and the world is paused after each success. An invalid keyframe produces no epoch change and every failure path ends paused.
single_variable: Runtime dependency changes from apt-only 0.0.3 to the exact pinned 0.0.3 commit plus approved reset hook patch; transaction order, timeouts, freshness, step count, model, controllers, and tolerances remain frozen from EXP-022.
lifecycle: FULL_RESTART
preconditions:
  - Task 10A commit d93bba347c2dbd5794c223a9e88f976286a736a8 and patch SHA-256 367cf5e3eab641412e234a3b1db86922b5573704932e950f98d9ca394056ea9f pass upstream, project, provenance, Ruff, isolation, and protected-tree gates.
  - Source order is /opt/ros/jazzy then /data/work/ws_mujoco_ros2_control_003/install then project install; all package prefixes and installed hashes match dependency-lock.yaml.
  - ROS_DOMAIN_ID 105 is empty before launch; session is task-owned and unique; no MoveIt, GUI, motion workflow, or hardware.
success_criteria:
  - Two receipts each increment epoch exactly one and form a contiguous sequence.
  - Four pause-window records have finite object position, linear/angular velocity and six joints; object error is at most 0.003 m and each joint error at most 0.002 rad.
  - Both controllers are active after verification; final world is paused; invalid-keyframe/failure checks leave paused and do not increment epoch.
failure_criteria:
  - Any switch/service timeout, epoch delta other than one, missing/nonfinite record, tolerance failure, inactive controller, non-paused final/failure state, or invalid keyframe epoch change.
invalid_criteria:
  - Prefix/hash/session/domain mismatch, stale build, cross-domain contamination, incomplete owned-process cleanup, or missing raw logs.
provenance:
  source_commit: d93bba347c2dbd5794c223a9e88f976286a736a8 plus the preserved eight Task 10 paths
  dependency_checkout: /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control at 35ba8174b62d9560093614f981a3d4b978a96036 plus exact approved patch
  dependency_overlay: /data/work/ws_mujoco_ros2_control_003/install
  project_install: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  ros_domain_id: 105
  simulation_session_id: exp023-reset-qualified-domain105
  evidence_path: /tmp/so101-debug-mujoco-migration/exp-023/
owned_processes: Task-owned tmux session so101-mujoco-exp023, pane PID 4086219, launch PID 4086310, robot_state_publisher PID 4086317, and ros2_control_node PID 4086319 were recorded, stopped, reaped, and verified absent; domain 105 is empty after cleanup.
observed:
  - The first task_start transaction completed strict deactivate while running, pause, successful ResetWorld, resume, strict activate, re-pause, and bounded step. Server logs show both controller switches succeeded and reset returned success.
  - The reset hook produced the expected new epoch and the transaction reached physical verification, but it failed the unchanged six-joint 0.002 rad convergence gate before a first receipt was returned.
  - Post-failure list_controllers showed joint_state_broadcaster, arm_controller, and gripper_controller active. The failure-finally pause prevented a live evidence echo while paused; the captured joint state was [-0.0000492087, 0.0139146102, 0.0158319298, 0.0029935284, 0.0000038187, -0.0000460467] rad, exceeding tolerance on joints 2, 3, and 4.
  - Because the first receipt failed, the second reset, four-record qualification, and invalid-keyframe check were not executed and cannot be claimed.
inferred:
  - The approved hook resolves the absent epoch trigger, but EXP-023 does not qualify Task 10 because post-reset controller/joint convergence is physically outside the frozen threshold.
conclusion: INVALID at the joint convergence hard gate; no Task 10 production commit is allowed and no tolerance/order patch is justified without a new evidence-layer experiment.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-023/live-reset-contract.log
  - /tmp/so101-debug-mujoco-migration/exp-023/server-tail-after-failure.txt
  - /tmp/so101-debug-mujoco-migration/exp-023/joints-after-failure.yaml
  - /tmp/so101-debug-mujoco-migration/exp-023/controllers-after-failure.txt
  - /tmp/so101-debug-mujoco-migration/exp-023/process-tree-after-failure.txt
  - /tmp/so101-debug-mujoco-migration/exp-023/evidence-sha256.txt
decision: STOP; preserve dirty Task 10 work and request revised experiment direction.
next_command: NONE
```

## Checkpoint CP-025

```yaml
checkpoint_id: CP-025
last_valid_experiment: EXP-019
current_hypothesis: NONE; reset epoch authority is now observable, but the first reset fails the unchanged joint convergence hard gate.
working_tree_status: Task 10A is committed at d93bba347c2dbd5794c223a9e88f976286a736a8. The eight Task 10 paths remain dirty and unstaged, including the paused-start RED/GREEN and expanded live assertions; no protected Gazebo path changed.
owned_processes: NONE; so101-mujoco-exp023 and recorded PIDs 4086219, 4086310, 4086317, 4086319 were stopped/reaped, and ROS_DOMAIN_ID 105 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - The reset-qualified overlay passes its build, upstream 114-test suite, exact provenance/hash gate, project build/tests, Ruff, isolation, and protected-tree gates.
  - The patched central reset creates an observable epoch transition and reaches atomic postcondition verification.
  - EXP-023 fails the frozen 0.002 rad joint gate on joints 2, 3, and 4 after the first reset despite active controllers and successful service ordering.
disproven_routes:
  - The missing epoch trigger is no longer the first Task 10 boundary.
  - A successful ResetWorld response, successful controller activation, and new epoch are insufficient to claim deterministic reset when joint state is outside tolerance.
open_risks:
  - The cause and time evolution of the 0.0139/0.0158/0.0030 rad residual joint errors are not yet characterized; changing tolerance, step count, deadline, controller commands, or transaction order would be guessing.
next_command: NONE
```

## Checkpoint CP-026

```yaml
checkpoint_id: CP-026
last_valid_experiment: EXP-024
current_hypothesis: The live-test-only 20-step override causes the first post-reset joint divergence; the canonical five-step default should establish the new epoch without exceeding 0.002 rad.
working_tree_status: Exact eight Task 10 paths remain dirty and unstaged on HEAD d93bba347c2dbd5794c223a9e88f976286a736a8; no protected Gazebo path changed.
owned_processes: NONE; exp024-joint-boundary-domain106 and recorded PIDs 4103494, 4103700, 4103728, and 4103729 were stopped/reaped, and ROS_DOMAIN_ID 106 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-024 is VALID diagnostic evidence: controller activation ends within 0.000066 rad of home, while paused StepSimulation(20) produces a fresh 0.0144914167 rad maximum joint error.
  - Joint and evidence callbacks advance across the step boundary, disproving stale verification data.
  - The approved plan requires a bounded step but does not require 20; production already defaults to five while the live contract alone overrides it to 20.
disproven_routes:
  - Resume/activate is not the first joint divergence boundary.
  - Increasing joint tolerance or changing the frozen transaction order is unsupported by current evidence.
open_risks:
  - Five steps may be insufficient to publish the first authoritative reset epoch, or may still exceed the joint tolerance; EXP-025 must decide this before any source change.
  - Evidence pause-state authority after manual stepping remains unresolved and is not part of the EXP-025 single variable.
next_command: Execute preregistered EXP-025 on fresh ROS_DOMAIN_ID 107 with only step_count changed from 20 to 5.
```

## Checkpoint CP-027

```yaml
checkpoint_id: CP-027
last_valid_experiment: EXP-024
current_hypothesis: NONE; the preregistered five-step A/B failed both the frozen joint gate and the paused-evidence freshness requirement.
working_tree_status: Exact eight Task 10 paths remain dirty and unstaged on HEAD d93bba347c2dbd5794c223a9e88f976286a736a8; no protected Gazebo path changed and the index remains untouched.
owned_processes: NONE; so101-mujoco-exp025 pane 4117905 and its recorded child stack were stopped/reaped, and ROS_DOMAIN_ID 107 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-025 changes only step_count from 20 to 5 under the same qualified overlays, model, transaction, thresholds, controllers, and fresh-stack lifecycle.
  - Five steps advance the authoritative epoch and reduce maximum joint error from EXP-024's 0.0144914167 rad to 0.002323864095551104 rad, but joint 3 still violates 0.002 rad.
  - No subsequent paused evidence is published, so the original deadline ends in typed EvidenceStale despite active controllers and finite object/joint samples.
disproven_routes:
  - Replacing the live-test 20-step override with the production five-step default is not sufficient to qualify Task 10.
  - Further step-count tuning is not supported because it would combine physical convergence with the unresolved pause-state/evidence-publication boundary.
open_risks:
  - Atomic evidence does not currently publish an authoritative paused state after manual stepping; the last fresh message reports paused false and then becomes stale.
  - The minimum bounded step that both exposes the new reset generation and preserves the 0.002 rad joint gate has not been established and must not be guessed.
next_command: NONE
```

## Checkpoint CP-028

```yaml
checkpoint_id: CP-028
last_valid_experiment: EXP-024
current_hypothesis: The joint violation and paused-evidence failure are separate boundaries: unrealistically weak kp=1 position actuators permit gravity drift, while the plugin has no authoritative pause-state input.
working_tree_status: Exact eight Task 10 paths remain dirty and unstaged on HEAD d93bba347c2dbd5794c223a9e88f976286a736a8; this ledger-only diagnostic checkpoint is the only new worktree edit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - The 0.0.3 physics loop executes paused pending steps and advances /clock; controller_manager read/update/write runs at 500 Hz from simulation time.
  - The evidence plugin is invoked only from hardware read(), infers paused from equality with its prior publish time, and receives neither sim_->run nor SetPause state.
  - A manual paused step advances data->time, so the only post-step evidence is necessarily labeled paused=false; after stepping stops, /clock stops and no later plugin update can publish paused=true.
  - The production MJCF declares kp=1 for all six position actuators; at exact home, zero position error produces no actuator torque to balance gravity.
disproven_routes:
  - Executor retries or a longer EvidenceStale timeout cannot create a paused update after simulation time stops.
  - The current time-equality heuristic cannot provide authoritative pause state for StepSimulation snapshots.
open_risks:
  - Adding authoritative pause state requires an explicit runtime-to-plugin signal not present in the approved on_reset-only base hook; this architecture must be revised before Task 10 can qualify.
  - The contribution of kp=1 to the five-step joint error is strongly indicated but not yet isolated in an offline same-model A/B.
next_command: Execute preregistered offline EXP-026; do not modify production MJCF or runtime APIs.
```

## Experiment EXP-026

```yaml
experiment_id: EXP-026
status: INVALID
prior_experiment: EXP-025
hypothesis: The production MJCF's kp=1 position-actuator stiffness is sufficient to explain the five-step home drift under gravity.
prediction: From the exact task_start keyframe with identical model state and zero control targets, the current kp=1 model exceeds 0.002 rad within five steps, while a diagnostic-only uniform kp=50 copy remains within 0.002 rad.
single_variable: Uniform position actuator kp changes from 1 to 50 in an evidence-directory copy; geometry, inertial, timestep, keyframe, ctrl, solver, and step count remain identical.
lifecycle: OFFLINE_MODEL_AB
preconditions:
  - Load the exact installed/project MJCF and assets corresponding to HEAD d93bba347c2dbd5794c223a9e88f976286a736a8 plus preserved dirty Task 10 paths.
  - Write all copied/modified diagnostic assets and results only below /tmp/so101-debug-mujoco-migration/exp-026/.
success_criteria:
  - Both models compile and produce finite five-step qpos/qvel traces from task_start.
  - A exceeds 0.002 rad and B remains within 0.002 rad, isolating actuator kp as a causal model parameter.
failure_criteria:
  - Both variants exceed the threshold or changing kp does not materially reduce the same joint errors.
invalid_criteria:
  - Any non-kp XML difference, different initial keyframe/control, missing asset, nonfinite state, or production-tree write.
provenance:
  source_commit: d93bba347c2dbd5794c223a9e88f976286a736a8 plus preserved eight Task 10 paths
  source_mjcf: src/so101_mujoco_demo_py/mjcf/so101.xml
  evidence_path: /tmp/so101-debug-mujoco-migration/exp-026/
commands:
  - command: Offline exact-model A/B diagnostic
    exit_code: 0
observed:
  - Both exact scene copies compiled and produced finite qpos/qvel through five 0.002 s steps from the task_start keyframe with zero controls.
  - A with kp=1 reached maximum absolute joint error 0.0009733845952399659 rad at step five.
  - B with uniform kp=50 reached 0.0009534146652874344 rad at step five, only about two percent lower; both remained below 0.002 rad.
  - The exact A/B file diff contains only the six declared kp values, and A hashes match the production MJCF inputs.
inferred:
  - Uniform stiffness 1 to 50 is not the causal explanation for the runtime five-step violation.
  - EXP-025 begins its explicit five-step service after activation has already advanced the reset model to approximately the direct model's third-step state; its final 0.002323864 rad corresponds to more accumulated physics than the preregistered zero-state five-step A/B.
conclusion: INVALID hypothesis: kp=1 does not explain the discrepancy, and changing production actuator stiffness is unsupported.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-026/a-result.json (sha256 ed61b889a836922dfec648e74e6e84ee4e1c11b413178c9ff920f5171b8f472f)
  - /tmp/so101-debug-mujoco-migration/exp-026/b-result.json (sha256 55c23673020415ecef1961e1ebb41d91bad4e4643bf81b8752eb8de6e2f2827c)
  - /tmp/so101-debug-mujoco-migration/exp-026/model-diff.patch (sha256 cebc24ca013643a69679c3def356122b30f06ba049848d023ef6218faa968444)
  - /tmp/so101-debug-mujoco-migration/exp-026/offline_kp_ab.cpp (sha256 67ae3cffd058a5f161c015921d305368c74ccaaea78c23c3062778cebe02d3a3)
decision: DROP actuator-stiffness patch route; retain the independently proven pause-authority architecture gap and stop before proposing a new physical experiment.
next_experiment: NONE
```

## Checkpoint CP-029

```yaml
checkpoint_id: CP-029
last_valid_experiment: EXP-024
current_hypothesis: NONE; actuator stiffness was disproven, while authoritative pause-state publication remains an implementation-interface gap requiring architecture approval.
working_tree_status: Exact eight Task 10 paths remain dirty and unstaged on HEAD d93bba347c2dbd5794c223a9e88f976286a736a8; only this ledger records the new read-only diagnosis and offline experiment.
owned_processes: NONE; EXP-026 was offline and launched no ROS, tmux, simulator, MoveIt, GUI, or hardware process.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - Exact-model five-step drift from task_start is 0.0009733845952399659 rad at kp=1, below the frozen 0.002 rad gate.
  - Uniform kp=50 changes that result only to 0.0009534146652874344 rad, disproving stiffness as the runtime discrepancy's cause.
  - EXP-025's explicit five-step phase starts after activation has already advanced the model to about the direct trace's third-step state, so total post-reset physics advancement—not five steps from zero—explains the larger observed error.
  - The pause field remains structurally non-authoritative: the base plugin API exposes only model/data during update and the approved on_reset hook, while SetPause state exists only as sim_->run in the system interface.
disproven_routes:
  - Raising position-actuator kp is unsupported and must not be committed.
  - Timeout/executor changes cannot produce a paused snapshot after /clock and controller updates stop.
open_risks:
  - Task 10's mandatory four paused atomic records cannot be proven without an explicit authoritative pause signal reaching the evidence plugin.
  - Any change to the approved upstream hook beyond on_reset is an architecture change and requires user/orchestrator approval before implementation.
  - A new physical A/B must isolate the uncommanded activation-window physics advancement before altering step count or transaction order.
next_command: NONE
```

## Checkpoint CP-030

```yaml
checkpoint_id: CP-030
last_valid_experiment: EXP-024
current_hypothesis: A minimal runtime pause notification plus reset-generation priority over the evidence rate gate can make one paused step produce authoritative epoch evidence while staying within the frozen joint threshold.
working_tree_status: Exact eight Task 10 paths remain dirty and unstaged on HEAD d93bba347c2dbd5794c223a9e88f976286a736a8; only ledger checkpoints were added during this architecture audit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - The plugin currently checks its 0.01 s publish period before loading/consuming reset_generation, so a 0.002 s paused step cannot expose the new epoch even though update() runs.
  - EXP-026's exact-model trace proves total post-reset step four has maximum joint error 0.0006500513951707087 rad, whereas EXP-025's effective total step eight is outside tolerance.
  - Therefore a one-step bounded service after the observed three-step activation window has evidence-backed joint margin, but it requires reset generation to bypass the ordinary publish-rate gate.
  - The approved on_reset-only base API still cannot make paused authoritative; a separate runtime-to-plugin pause signal is unavoidable.
proposed_contract_pending_approval:
  - Add default no-op virtual on_pause(bool paused) to the pinned 0.0.3 plugin base.
  - On every successful SetPause request, including idempotent requests, call each plugin exactly once with the authoritative requested state; failed service paths call zero times.
  - SimulationEvidencePlugin::on_pause performs only an atomic bool store; update() loads that value into the same locked mjData snapshot message and deletes time-equality inference.
  - A pending reset generation bypasses only the evidence publish-period throttle, so the first update after reset consumes the generation; normal publish cadence remains fixed.
  - Set the Task 10 bounded step count to one, retain the original deadline and typed-EvidenceStale-only retry, and change no physics threshold or transaction ordering.
required_red_tests:
  - Disposable upstream patch replay proves default-compatible on_pause signature and exactly-once success/idempotent notification with zero failed-path notification.
  - Support plugin test proves on_pause true/false is reflected by update independent of simulation-time movement and that pending generation publishes before 0.01 s.
  - Python transaction test proves one bounded step and preserves running deactivate -> pause -> ResetWorld -> resume -> activate -> re-pause -> step -> atomic verify.
  - Fresh live two-reset qualification proves consecutive epochs, four finite paused records, joints <=0.002 rad, object <=0.003 m, controllers active, final/failure paused, and invalid keyframe zero epoch change.
open_risks:
  - This expands the user-approved upstream patch API beyond on_reset and cannot be implemented without explicit architecture approval.
  - EXP-026 is offline support for the one-step prediction; live behavior remains unproven until a preregistered fresh-domain experiment.
next_command: NONE
```

## Checkpoint CP-031

```yaml
checkpoint_id: CP-031
last_valid_experiment: EXP-024
current_hypothesis: The approved on_pause hook, pending-generation priority, and one-step bounded transaction jointly satisfy authoritative paused evidence and the unchanged reset physical gates.
working_tree_status: Task 10 implementation remains deliberately dirty and unstaged on HEAD e0838b0b8d76ee17620a998931fa57718b0b284d; the protected Gazebo tree remains untouched.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - User approved the CP-030 architecture and spec/plan commit e0838b0b8d76ee17620a998931fa57718b0b284d records it independently.
  - Overlay RED failed for absent on_pause; GREEN patch replay tests pass 10/10, upstream tests pass 114/114, and the installed patch/provenance SHA is 19d4d8adc45858cd441c1ce5f2887063fe3b17b08d94e67c400a6c9effe6380b.
  - Support RED failed to compile without on_pause; GREEN integration passes seven tests and proves authoritative pause plus reset-generation publication at 0.001 s while ordinary messages remain rate limited.
  - Python RED failed for step five and accepting non-paused new-epoch evidence; GREEN focused reset tests pass 13/13 with exactly one step and paused postcondition.
  - The first two-package test run has only the expected stale-ledger next_experiment failure: support 7 passed; Python 109 passed, 1 failed, 2 opt-in skipped.
open_risks:
  - Four pause-window records and two consecutive live reset cycles remain unproven until EXP-027.
  - An in-flight control update must publish the first pause window; the post-step generation-priority update must publish the second.
next_command: Run the corrected package gate, then execute preregistered EXP-027 only if all static/provenance/isolation preconditions pass.
```

## Experiment EXP-027

```yaml
experiment_id: EXP-027
status: INVALID
prior_experiment: EXP-026
hypothesis: The approved authoritative pause hook, pending-reset publication priority, and one-step bounded transaction make two consecutive task_start resets deterministic without relaxing any physical threshold.
prediction: Both resets increment epoch exactly once and return within the original deadline; four finite pause-window atomic records report paused=true; object error is <=0.003 m, every joint error <=0.002 rad, controllers remain active, final state is paused, and an invalid keyframe leaves epoch unchanged with failure paused.
single_variable: Approved CP-030 implementation replaces time-derived pause with on_pause authority, prioritizes pending reset generation, and changes bounded step count from five to one; transaction order, timeout, model, controllers, and thresholds are unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD e0838b0b8d76ee17620a998931fa57718b0b284d plus preserved Task 10 dirty implementation and freshly built two-package overlay.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; exact lock/provenance and package gates pass.
  - Fresh task-owned ROS_DOMAIN_ID 109 and session exp027-authoritative-pause-domain109; no MoveIt, GUI, workflow motion, or hardware.
success_criteria:
  - Two receipts form consecutive epoch pairs with each increment exactly one and simulation_step > 0.
  - Exactly four pause-window records are finite and authoritative paused=true.
  - Object position error <=0.003 m, all six joints <=0.002 rad, controllers active, and final state paused.
  - Invalid keyframe produces ResetFailed, leaves epoch unchanged, and leaves authoritative state paused.
failure_criteria:
  - Any frozen postcondition, service order, deadline, epoch, pause, controller, joint, object, or invalid-keyframe assertion fails with complete evidence.
invalid_criteria:
  - Stale build/prefix, contaminated domain, missing record, source-order mismatch, executor failure, or incomplete task-owned cleanup.
provenance:
  source_commit: e0838b0b8d76ee17620a998931fa57718b0b284d plus preserved Task 10 dirty paths
  upstream_commit: 35ba8174b62d9560093614f981a3d4b978a96036
  patch_sha256: 19d4d8adc45858cd441c1ce5f2887063fe3b17b08d94e67c400a6c9effe6380b
  dependency_overlay: /data/work/ws_mujoco_ros2_control_003/install
  project_install: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  ros_domain_id: 109
  gz_partition: NONE
  evidence_path: /tmp/so101-debug-mujoco-migration/exp-027/
commands:
  - command: SO101_MUJOCO_RESET_LIVE_TEST=1 package live contract against fresh headless stack
    exit_code: 1
observed:
  - The first reset completed strict deactivate, pause, successful task_start ResetWorld, resume, strict activate, re-pause, and StepSimulation(1); server-side service ordering contains no timeout or failure.
  - The transaction did not raise the immediate non-paused, session, epoch-ahead, controller, joint, or object failures; it exhausted the unchanged 10 s deadline while paused at the legacy current.simulation_step > 0 gate.
  - No first receipt was returned; therefore the second reset, four-record qualification, and invalid-keyframe checks did not execute and cannot be claimed.
  - Task-owned pane 4167162 and children were stopped/reaped; ROS_DOMAIN_ID 109 was empty after cleanup and unrelated sessions remained.
inferred:
  - The installed builder resets simulation_step to zero when it consumes a generation, and the one-step service provides no later update; correlated source and service evidence therefore predicts the only new-epoch observation is authoritative step zero, but EXP-027 did not print the message and cannot promote that prediction to a direct observation.
  - The next diagnostic must print the post-step atomic key/paused/object/joint state before changing the Python gate.
  - Adding more steps to manufacture a positive counter would recreate the disproven joint-drift route and is not justified.
conclusion: INVALID for Task 10 qualification because the Python postcondition rejected the schema-authoritative reset step zero and timed out before any receipt.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-027/live-reset-contract.log (sha256 3e72bacc667323ad05a83a26fa643fe769122bfe174a8abe8d181eb41ed16dc2)
  - /tmp/so101-debug-mujoco-migration/exp-027/launch.log (sha256 64d7ae5005a5d2deba85e5942245334b12d20f15642375bf2b613b194c108fb2)
  - /tmp/so101-debug-mujoco-migration/exp-027/provenance.json (sha256 b6de0ad2088f540c2465ad98a3145eaba997080d849d2a023eaecdd7239eac03)
  - /tmp/so101-debug-mujoco-migration/exp-027/runtime-hashes.txt (sha256 833da975dc64fd317e6afdfd7f900f01aa36a37f80ad0f01d3f7e7ff9fac46bb)
decision: STOP; preserve the one-step physical route and request/record explicit acceptance of reset-generation step zero before changing the Python postcondition.
next_experiment: NONE
```

## Checkpoint CP-032

```yaml
checkpoint_id: CP-032
last_valid_experiment: EXP-024
current_hypothesis: The one-step transaction publishes only the schema-authoritative new-epoch step-zero snapshot, which the legacy Python >0 gate ignores; direct atomic-key capture is required before changing that gate.
working_tree_status: Approved overlay/support/Task 10 changes remain dirty and unstaged on HEAD e0838b0b8d76ee17620a998931fa57718b0b284d; no protected Gazebo path changed.
owned_processes: NONE; so101-mujoco-exp027 pane 4167162 and children were stopped/reaped, and ROS_DOMAIN_ID 109 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-027 completes the exact one-step service transaction through re-pause and fails only by exhausting the Python postcondition deadline before a first receipt.
  - The frozen builder contract assigns simulation_step zero on generation consumption; with only one paused step there is no subsequent clock/update to increment it.
  - Raising the step count is rejected because prior evidence proves accumulated post-reset physics crosses the unchanged joint threshold.
disproven_routes:
  - The approved on_pause overlay does not reproduce the earlier controller switch timeout.
  - More timeout cannot change the atomic key after the paused clock stops.
open_risks:
  - EXP-027 did not serialize its last atomic message, so step-zero/paused/new-epoch correlation remains a source-backed prediction rather than direct black-box evidence.
  - Four pause-window records, two receipts, invalid keyframe, and full Task 10 qualification remain incomplete.
next_command: NONE
```

## Checkpoint CP-033

```yaml
checkpoint_id: CP-033
last_valid_experiment: EXP-024
current_hypothesis: The one-step transaction produces a fresh authoritative tuple (session, new_epoch, step=0, paused=true) with physical state inside unchanged gates; direct black-box capture can confirm or reject it without changing production.
working_tree_status: Approved overlay/support/Task 10 changes remain dirty and unstaged on HEAD e0838b0b8d76ee17620a998931fa57718b0b284d; no protected Gazebo path changed.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-027 failed before a receipt because the legacy Python gate requires simulation_step > 0 after a builder-defined step-zero generation observation.
  - The exact service order and one-step operation complete without controller-switch or service timeout.
open_risks:
  - The post-step atomic tuple and physical values were not serialized by EXP-027 and must be observed directly before changing the gate.
next_command: Execute preregistered EXP-028 on fresh domain 110 without invoking MujocoResetClient.
```

## Experiment EXP-028

```yaml
experiment_id: EXP-028
status: INVALID
prior_experiment: EXP-027
hypothesis: One successful paused StepSimulation(1) after the approved reset transaction publishes exactly the new reset epoch at simulation_step zero with authoritative paused=true and physical state inside the unchanged gates.
prediction: Direct boundary capture shows reset_epoch old+1, simulation_step=0, paused=true, finite object/joint state, object error <=0.003 m, every joint <=0.002 rad, and active controllers immediately after step one.
single_variable: Measurement only: replace MujocoResetClient postcondition loop with direct service calls and serialized observer samples; build, model, order, one-step count, controllers, timeout, and thresholds are unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD e0838b0b8d76ee17620a998931fa57718b0b284d plus preserved approved dirty Task 10 implementation and freshly built overlays.
  - Source order /opt/ros/jazzy -> dependency overlay -> project install and exact patch/provenance pass.
  - Fresh task-owned ROS_DOMAIN_ID 110 and session exp028-step-zero-domain110; no MoveIt, GUI, workflow motion, or hardware.
success_criteria:
  - Every service returns true in the frozen order and the post-step callback is fresh.
  - The direct post-step tuple is new_epoch, step zero, paused true; object/joints are finite and inside unchanged thresholds; controllers are active.
failure_criteria:
  - Direct evidence contradicts any predicted key, pause, physical, controller, or service property.
invalid_criteria:
  - Stale build/prefix, contaminated domain, missing callback, executor failure, or incomplete task-owned cleanup.
provenance:
  source_commit: e0838b0b8d76ee17620a998931fa57718b0b284d plus approved dirty Task 10 paths
  upstream_commit: 35ba8174b62d9560093614f981a3d4b978a96036
  patch_sha256: 19d4d8adc45858cd441c1ce5f2887063fe3b17b08d94e67c400a6c9effe6380b
  ros_domain_id: 110
  evidence_path: /tmp/so101-debug-mujoco-migration/exp-028/
commands:
  - command: Fresh stack plus manual one-step boundary capture
    exit_code: 1
observed:
  - Strict deactivate, pre-reset pause, task_start reset, resume, strict activate, re-pause, and StepSimulation(1) all returned success in the frozen order.
  - The observer received no new-epoch callback within two seconds after the successful one-step service and the diagnostic raised new-epoch post-step callback timeout.
  - Because no post-step atomic record existed, no step, pause, object, joint, or controller success property can be claimed from this run.
  - Task-owned pane 2823 and its child stack were stopped/reaped; domain 110 was empty after cleanup and unrelated sessions remained.
inferred:
  - One clock increment is insufficient to guarantee that the controller-manager read loop invokes the plugin after reset; pending-generation rate bypass cannot publish without an update invocation.
  - EXP-027's timeout was absence of a new-epoch callback, not rejection of an observed step-zero record.
conclusion: INVALID hypothesis: StepSimulation(1) does not provide the required post-reset atomic observation.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-028/manual-capture.log (sha256 80b46bff4b120428757ab787765e85c3a458960dd35f2f8c2f82c2f96fe7f1bd)
  - /tmp/so101-debug-mujoco-migration/exp-028/launch.log (sha256 c3b526cf585451e3eda98a8da688a5b1a5d98abbce80d09f264aba4fe9fd81c1)
  - /tmp/so101-debug-mujoco-migration/exp-028/provenance.json (sha256 b6de0ad2088f540c2465ad98a3145eaba997080d849d2a023eaecdd7239eac03)
  - /tmp/so101-debug-mujoco-migration/exp-028/process-tree.txt (sha256 fce89ad63b8667a54d95b2e449c8c3c5f0753b2bf5fce9f79fc0b129d8b79320)
decision: STOP; do not change the Python step-zero gate. A new experiment must isolate the minimum clock advancement that invokes one post-reset control/plugin update while retaining the joint threshold.
next_experiment: NONE
```

## Checkpoint CP-034

```yaml
checkpoint_id: CP-034
last_valid_experiment: EXP-024
current_hypothesis: NONE; one paused step does not wake a post-reset controller/plugin update, while prior evidence bounds five paused steps outside the joint gate.
working_tree_status: Approved overlay/support/Task 10 changes remain dirty and unstaged on HEAD e0838b0b8d76ee17620a998931fa57718b0b284d; no protected Gazebo path changed.
owned_processes: NONE; so101-mujoco-exp028 pane 2823 and child stack were stopped/reaped, and ROS_DOMAIN_ID 110 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-028 directly proves a successful StepSimulation(1) produces no observable new-epoch callback within two seconds.
  - Pending-generation priority works when update() is invoked, as proven by the support integration test, but cannot itself wake controller_manager.
  - Accepting simulation_step zero in Python would not fix the observed runtime because no new-epoch message exists after one step.
disproven_routes:
  - The EXP-027 timeout must not be fixed by weakening current.simulation_step > 0.
  - One-step bounded reset cannot qualify Task 10 with the current 0.0.3 clock/controller scheduling boundary.
open_risks:
  - The minimum paused step count that wakes exactly one post-reset update is between two and five; it must be measured rather than guessed.
  - The corresponding accumulated joint error must remain <=0.002 rad and pause evidence must be authoritative.
next_command: NONE
```

## Checkpoint CP-035

```yaml
checkpoint_id: CP-035
last_valid_experiment: EXP-024
current_hypothesis: A subscriber active before the transaction can determine whether the one-step reset publishes a new-epoch step-zero paused message before, during, or after the explicit step boundary.
working_tree_status: All fifteen approved Task 10 dirty paths are preserved and unstaged on HEAD e0838b0b8d76ee17620a998931fa57718b0b284d; no production source is changed for this diagnostic.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - User approved the CP-032 recommended black-box route and explicitly requires pre-subscription plus serialization of every atomic message around one existing transaction.
  - EXP-028 is already terminal INVALID and cannot be reused without falsifying the append-only ledger; EXP-030 is its follow-up and repairs the EXP-028 instrumentation blind spot by pre-subscribing and persisting the complete callback stream across every service boundary.
open_risks:
  - The new generation may be published during resume/activate before the prior diagnostic begins its post-step wait, or no post-reset publication may occur at all.
next_command: Execute preregistered EXP-030 on fresh ROS_DOMAIN_ID 111; modify no production code, step count, deadline, or threshold.
```

## Experiment EXP-030

```yaml
experiment_id: EXP-030
status: INVALID
prior_experiment: EXP-028
supersedes_correction: EXP-030 corrects, but does not rewrite, EXP-028's unsupported inference that no new-epoch callback existed or that reset generation was unconsumed. EXP-028 is measurement INVALID because its exception path did not persist boundary events and it required a post-StepSimulation callback-count increase even when the new epoch could already have appeared during resume or activate.
hypothesis: Pre-subscribing and serializing every atomic message reveals exactly one new reset epoch with simulation_step zero and authoritative paused=true during the existing one-step transaction.
prediction: The complete callback stream contains exactly one epoch transition old->old+1; its first message has simulation_step=0 and paused=true with finite atomic object pose/twist and object error <=0.003 m, while the nearest asynchronous `/joint_states` sample has six finite joints inside 0.002 rad and independent controller feedback reports active controllers.
single_variable: Measurement coverage only: a raw atomic subscriber and joint recorder are running before the unchanged existing task_start transaction and serialize every callback before/after reset; production, one-step count, 10 s deadline, transaction order, model, controllers, and thresholds are unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD e0838b0b8d76ee17620a998931fa57718b0b284d plus exactly fifteen preserved Task 10 dirty paths and freshly built qualified overlays.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; exact prefix/header/runtime/patch provenance passes.
  - Fresh task-owned ROS_DOMAIN_ID 111 and session exp030-presubscribed-domain111; no MoveIt, GUI, workflow motion, hardware, or unrelated cleanup.
success_criteria:
  - The raw subscriber starts before transaction entry and records every publisher sequence with session, epoch, step, paused, atomic object pose/twist, the nearest asynchronous `/joint_states` sample, and boundary label; the joint sample is not represented as part of or correlated with the atomic message.
  - New epoch appears exactly once, first new-epoch record is step zero and paused true, all physical values are finite and inside unchanged gates, and controllers are active.
failure_criteria:
  - No new epoch, more than one increment, nonzero first step, paused false, invalid/missing physical/controller state, or unchanged transaction failure inconsistent with the prediction.
invalid_criteria:
  - Subscriber not ready before transaction, stale build/prefix, contaminated domain, dropped/duplicate publisher sequence, executor failure, or incomplete task-owned cleanup.
provenance:
  source_commit: e0838b0b8d76ee17620a998931fa57718b0b284d plus fifteen preserved Task 10 paths
  upstream_commit: 35ba8174b62d9560093614f981a3d4b978a96036
  patch_sha256: 19d4d8adc45858cd441c1ce5f2887063fe3b17b08d94e67c400a6c9effe6380b
  ros_domain_id: 111
  evidence_path: /tmp/so101-debug-mujoco-migration/exp-030/
commands:
  - command: Pre-subscribed raw evidence recorder plus existing MujocoResetClient.reset(task_start)
    exit_code: 1
observed:
  - The raw subscriber was receiving before transaction entry and recorded eight strictly increasing publisher sequences 1193 through 1200 without a duplicate or reversal.
  - Exactly one new-epoch record appeared: publisher_sequence 1200, session exp030-presubscribed-domain111, reset_epoch 1 from old epoch 0, simulation_step 0, boundary during:activate, and paused=false.
  - That record's object pose was exactly [0.27, 0.0, 0.08] with identity orientation and zero linear/angular twist, all finite and inside the 0.003 m gate.
  - The `joint_positions` stored beside that record are the nearest asynchronous `/joint_states` sample, not a field of the atomic evidence message and not correlated to the same service boundary. That independent sample was still pre-reset [0.0013423323, 1.0616174434, 0.3767800378, 0.0833674276, 0.0000935846, -0.0021920242] rad and cannot qualify a converged atomic joint record.
  - Re-pause and StepSimulation(1) returned success but produced no later atomic message. Independent final controller feedback reported active controllers and joints [-0.0000006392, 0.0001658372, 0.0001956669, 0.0000360990, 0.0000000458, -0.0000005113] rad, within 0.002, but it is not correlated with any same-boundary paused atomic record.
  - MujocoResetClient exhausted the unchanged deadline; task-owned pane 12149 and children were stopped/reaped and domain 111 was empty after cleanup.
inferred:
  - Pending generation is consumed during the running activation window before re-pause, so the sole new-epoch step-zero record correctly reports authoritative paused=false.
  - One paused step is insufficient to cause another plugin publish; physical/controller convergence alone cannot substitute for the missing paused atomic record.
conclusion: INVALID because the user-mandated black-box prerequisite paused=true with valid atomic object state and independently qualified joint/controller feedback is false.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-030/all-atomic-evidence.json (sha256 984f6b1e16b1d64ec0715f2a61a24fdc42a03883d501965849fde21c3058e34f)
  - /tmp/so101-debug-mujoco-migration/exp-030/pre-subscribed-capture.log (sha256 cbf918ef30190683458340dffa2513c0d7850cda1282fe70f82d6aea008691db)
  - /tmp/so101-debug-mujoco-migration/exp-030/launch.log (sha256 2216293f24d5ecd501fcd5223a7741011adac2c759eed4408b5c38be1ec46348)
  - /tmp/so101-debug-mujoco-migration/exp-030/provenance.json (sha256 b6de0ad2088f540c2465ad98a3145eaba997080d849d2a023eaecdd7239eac03)
  - /tmp/so101-debug-mujoco-migration/exp-030/runtime-hashes.txt (sha256 1e0994ea61424277d7e3f21a70366c1a395df8503c859d6459c8c9166c3d1b0e)
  - /tmp/so101-debug-mujoco-migration/exp-030/domain-after-domain111-node-list-no-daemon.txt (empty; sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
decision: STOP as explicitly required; do not add the step-zero ResetReceipt test or modify reset.py because the iff prerequisite did not hold.
next_experiment: NONE
```

## Checkpoint CP-036

```yaml
checkpoint_id: CP-036
last_valid_experiment: EXP-024
current_hypothesis: NONE; the approved iff prerequisite is directly false because the only new-epoch step-zero message is published during activate with paused=false and no later paused atomic record exists after one step.
working_tree_status: All fifteen Task 10 dirty paths remain preserved and unstaged on HEAD e0838b0b8d76ee17620a998931fa57718b0b284d; no production change followed the failed black-box prerequisite.
owned_processes: NONE; so101-mujoco-exp030 pane 12149 and child stack were stopped/reaped, and ROS_DOMAIN_ID 111 is empty.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - Pre-subscription captured the complete relevant stream and proves exactly one epoch increment, first step zero, but paused=false during activate.
  - Re-pause plus one explicit step produces no further atomic publication. Independent final controller feedback reports active controllers and joints within 0.000196 rad, but is not an atomic field and is not correlated to the paused evidence boundary.
  - The object state in the new-epoch message is exact and finite. The adjacent `joint_positions` value is only the nearest asynchronous `/joint_states` sample, is pre-reset, and cannot qualify a same-boundary atomic physical gate.
  - EXP-030 supersedes only the interpretation of EXP-028, preserving its historical record: EXP-028's exception path omitted persisted boundary events and its forced post-step callback-delta wait missed the new epoch already published during activate. EXP-028 is therefore measurement INVALID and cannot support its former inferred claims that no new-epoch callback existed or generation was unconsumed.
  - The prior `domain-after.txt` was produced through the ROS 2 daemon and listed nodes cached from the default domain; it is a daemon artifact, not domain-111 cleanup evidence. A fresh `ROS_DOMAIN_ID=111 ros2 node list --no-daemon` produced the empty `domain-after-domain111-node-list-no-daemon.txt` with sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855, directly verifying domain 111 empty without stopping any additional process.
disproven_routes:
  - The user-approved condition for accepting step-zero ResetReceipt is not satisfied, so test_mujoco_reset.py and reset.py must remain unchanged by this route.
  - Plan/action/service success, converged final joints, or a step-zero epoch alone cannot establish authoritative paused atomic success.
open_risks:
  - The approved one-step CP-030 transaction cannot publish a post-re-pause atomic message under the current controller/plugin scheduling boundary.
  - Any next route would require new user direction because increasing steps, changing order, or adding another runtime publication hook is outside the explicit iff authorization.
next_command: NONE
```

## Checkpoint CP-006

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-001
current_hypothesis: The independent Python contracts can faithfully represent the expanded atomic ROS message without backend leakage.
working_tree_status: Clean at Task 4 implementation commit 6d598b8340b50925c217e5a9a088ab600156099a; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent support package publishes session, reset epoch, simulation step, publisher sequence, pause, object state, aggregate contact metrics, and separate left/right/other contact arrays.
  - Model-backed GTest passed 5 of 5; aggregate colcon results contain 246 tests, zero errors, zero failures, and two pre-existing skips.
  - Message interface and pluginlib export were verified from the installed Task 4 overlay.
  - Static read-only scan found no qpos/qvel writes, reset/set calls, equality, weld, adhesion, or mocap operations in the plugin implementation.
disproven_routes:
  - Incrementing simulation_step on a paused same-time publication is invalid; the builder now holds step constant while publisher_sequence advances.
open_risks:
  - Live simulator publication and reset service correlation remain unproven until the launch/runtime tasks.
next_command: Start Task 5 RED tests for immutable backend-neutral Python evidence and provenance.
```

## Checkpoint CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_hypothesis: The pinned MuJoCo ROS 2 dependency can satisfy the required binary interface without a source fallback.
working_tree_status: Clean at Task 2 implementation commit 9c7889accfdb0eb253a2c9ef1b795b56fe680dad; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent ament_python package is commit 9c7889accfdb0eb253a2c9ef1b795b56fe680dad.
  - Package identity tests passed 5 of 5, the combined isolation suite passed 36 of 36, and the package-only colcon build completed successfully.
  - The installed resource marker and package manifest exist under the new package prefix, with no dependency on the protected package.
  - The protected tracked diff and protected status remained empty before and after the Task 2 implementation commit.
disproven_routes:
  - Running pytest with its cache provider inside implementation scope is incompatible with the fail-closed isolation scanner because generated node identifiers can contain rejected provenance strings.
open_risks:
  - No MuJoCo dependency interface or runtime behavior has been proven yet.
next_command: Start Task 3 with the apt mujoco_ros2_control 0.0.3 binary probe and define EXP-001 before any runtime-affecting experiment.
```

## Experiment EXP-001

```yaml
experiment_id: EXP-001
status: VALID
hypothesis: The installed apt mujoco_ros2_control 0.0.3 provider exactly satisfies the pinned package, prefix, file-hash, and service-interface contract.
independent_variable: Read-only execution of the dependency probe against the apt provider.
controlled_variables: ROS Jazzy underlay /opt/ros/jazzy; no overlay; no simulator; no ROS graph mutation; no hardware.
acceptance_criteria: Probe exit 0; all four prefixes equal /opt/ros/jazzy; control version starts 0.0.3-; exact ResetWorld, SetPause, and StepSimulation definitions; all pinned file SHA-256 values match.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-001-dependency-probe.json
owned_processes: NONE
result: Probe exit 0; all required prefixes, versions, interfaces, and pinned file hashes matched. Evidence SHA-256 is 8c2b83d7821f79e618c3ffaf5c6ead133853434367a28bf28d41e6ef978ab104.
next_command: NONE
```

## Checkpoint CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-001
current_hypothesis: Atomic evidence can be implemented against the proven apt 0.0.3 plugin API.
working_tree_status: Task 3 dependency lock, probe, contract tests, package dependencies, and this checkpoint are pending their single scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The apt provider is release 0.0.3 at /opt/ros/jazzy and no source fallback is required.
  - EXP-001 is VALID with exact versions, prefixes, service definitions, and file hashes recorded under the evidence root.
disproven_routes:
  - Floating main and unpinned source dependency resolution remain forbidden.
open_risks:
  - The Task 4 atomic evidence plugin has not yet been compiled against the proven API.
next_command: Run final Task 3 tests, package build, isolation gates, and create the scoped dependency commit.
```

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: A fail-closed physical-tree and Python AST scanner can enforce Task 1 isolation without touching protected content or runtime processes.
working_tree_status: The three Task 1 files contain the review fix and are pending one scoped implementation commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The Task 1 base is 45c6efc701b133c45875e86b0053cfc37dab7f4f and the pinned main base is d300e7a41fb274d6d7e120699b7040666ea61904.
  - The original implementation commit is 91c482bd609f7240d5f8547c968363135524bb4f.
  - The protected tracked diff and ordinary status are empty, and its pre-fix nontracked physical baseline digest is 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
  - Review RED produced 25 failures and 6 passes before the fix.
disproven_routes:
  - Case-sensitive best-effort text search cannot enforce package isolation.
  - Ordinary Git status cannot detect ignored or generated protected content.
open_risks:
  - The review fix implementation commit is not known until the scoped commit is created.
next_command: Run GREEN and all pre-commit gates, then create the scoped Task 1 review-fix commit.
```

## Checkpoint CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: NONE
working_tree_status: Clean at implementation commit e6489ee2949caf435fe028fbe7f65d30a371b5fb; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The fail-closed isolation implementation is commit e6489ee2949caf435fe028fbe7f65d30a371b5fb.
  - Review GREEN produced 31 passes, and the implementation commit passed its immediate isolation, protected-diff, protected-status, and clean-worktree gates.
  - The protected nontracked baseline remains 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
disproven_routes:
  - Case-sensitive text search, broad provenance exclusion, ordinary-status-only protection, and whole-repository backup scanning are not sufficient isolation gates.
open_risks:
  - No Task 1 repository-isolation risk remains; runtime migration experiments have not started.
next_command: Define EXP-001 before the first runtime-affecting migration experiment.
```

## Checkpoint CP-047

```yaml
checkpoint_id: CP-047
last_valid_experiment: EXP-034
current_hypothesis: NONE; Task 11 is fully qualified at its ROS-free boundary and no runtime experiment was authorized or required.
working_tree_status: HEAD c9ab83d0a94311a10db824841c9a36aa44e89c49; only the exact Task 11 workflow, motion, MoveIt, recovery, physical-outcome, policy, characterization-test, provenance, package metadata, CLI, and this ledger checkpoint paths are staged or dirty pending the scoped commit.
owned_processes: NONE; Task 11 started no ROS, MuJoCo, MoveIt, Gazebo, GUI, tmux, or hardware process.
preserved_processes: codex, kimi, and so101-py-qual remain untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - Every adapted behavior/config/metadata/test source was inspected individually from 8d7913e7f552a40ee627d65be8b873ac16748bc9 with git show and recorded in docs/provenance.json before implementation adaptation.
  - Characterization RED failed only because the new domain and physical-outcome modules did not exist; nine collection errors were preserved at /tmp/so101-debug-mujoco-migration/task-11/red-missing-modules.log with SHA-256 02f4597d7e6b41748a5443bad00f254a879cd920e75f823d47cfc4aed154eea7.
  - Final ROS-free pytest reports 160 passed and two opt-in live skips; review-driven RED/GREEN covers schema-v5 expected-world fields, safe v4 conversion, real resume/current-world validation, publisher-sequence/reset-epoch release correlation, offline plan_only, and direct Task 5 observer/reset bindings.
  - The two-package build passed, the two-package test run passed, and colcon test-result reports 412 tests, zero errors, zero failures, and four skips across retained aggregate results.
  - Schema v5 writes only backend-neutral expected-world fields; execute checkpoints require an injected expected-world provider, safe detached/unknown v4 checkpoints convert on read, and constrained, backend/session/policy/current-world mismatches or active release epochs fail closed for resume.
  - Release and recovery evidence consumes Task 5 SimulationEvidence through WorldObserver, release markers use the same publisher-sequence/reset-epoch domain as settle samples, and controlled recovery reset consumes WorldReset; no simulator-specific message or service type enters the business layer.
  - Ruff check/format, exact provenance validation, migration isolation, diff check, and protected Gazebo tracked/status gates pass.
  - The local origin/main ref is 32 commits behind HEAD and 91 commits ahead of HEAD; it was recorded only, with no fetch, rebase, merge, push, or branch mutation.
disproven_routes:
  - An unsourced ament shell cannot collect the package tests; the mandated overlay order resolves the package from the worktree build symlink.
  - Pytest cache under the implementation root is rejected by the isolation scanner; Task 11 test cache and ROS logs were redirected to the evidence root.
open_risks:
  - Live execute composition remains intentionally fail-closed with LIVE_RUNTIME_NOT_IMPLEMENTED until Task 12; ROS-free plan_only remains available and characterized.
  - Sandbox DDS socket creation emits transport warnings in the support GTest, but all nine support tests pass and no runtime graph is started.
next_command: Stage the exact Task 11 allowlist, verify the index and gates, commit feat(so101_mujoco): port pick place workflow, and do not push.
```

## Checkpoint CP-048

```yaml
checkpoint_id: CP-048
last_valid_experiment: EXP-034
current_hypothesis: NONE; Task 11 review fix round 1 is qualified at the ROS-free boundary and required no runtime experiment.
working_tree_status: HEAD 90e1411fc8c5bd3caf4bc1a97c21e5f6bdc919c8; only the three Task 11 production modules, their three characterization-test modules, and this ledger checkpoint are dirty pending the scoped review-fix commit.
owned_processes: NONE; no ROS graph, MuJoCo, MoveIt, Gazebo, GUI, tmux, or hardware process was started.
preserved_processes: codex, kimi, and so101-py-qual remain untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - Frozen source 8d7913e7f552a40ee627d65be8b873ac16748bc9 and the Task 11 brief require preserving the final-result schema. FinalPlacementSample therefore retains the compatibility gazebo_detached dataclass/wire field while backend-neutral business code uses simulator_detached; no Gazebo transport, message, service, or runtime dependency was introduced.
  - Schema-v4 gazebo_task_object_attached null is readable as an unknown constraint but cannot prove the physical workflow unconstrained. Resume now refuses it with RESUME_SIMULATOR_CONSTRAINT_UNKNOWN; true remains incompatible, false remains the only resumable conversion, and an active release epoch remains non-resumable.
  - Execute resume now requires a current-world provider and validates checkpoint TCP pose, gripper state, joint positions, MoveIt world-object poses, MoveIt attachment, task-object support, and required-world-object membership in addition to Task 5 simulator pose, stationarity, contact, session, backend, policy, and constraint evidence.
  - Release-settle samples retain simulation_time_s as source_timestamp_s and capture the true post-snapshot monotonic receipt time separately. Freshness remains enforced by the configured WorldObserver contract; the evaluator validates each clock independently and never subtracts different clock epochs.
  - Review RED produced the expected 11 failures and 19 controls passed; evidence is /tmp/so101-debug-mujoco-migration/task-11-fix1/review-red.log with SHA-256 57596e45ffd919e9323ca19e5f10abb9f8d2220ff24a7da0af1e5bfa4d52477c.
  - Focused GREEN passed 31 tests; full non-live Task 11 passed 171 with two live skips. The two-package build and test passed, and aggregate colcon test-result reports 423 tests, zero errors, zero failures, and four skips.
  - Ruff check/format, provenance tests, migration isolation, diff check, and protected Gazebo tracked/status gates pass. Evidence logs are rooted at /tmp/so101-debug-mujoco-migration/task-11-fix1/.
  - The local origin/main ref is 33 commits behind HEAD and 91 commits ahead of HEAD; it was recorded only, with no fetch, rebase, merge, push, or branch mutation.
disproven_routes:
  - Coercing a schema-v4 unknown attachment fact to false is not a safe compatibility conversion because it invents evidence needed for physical resume.
  - Subtracting simulation time from wall monotonic time is not a valid observation-age calculation because those values have independent epochs.
open_risks:
  - Live execute composition remains intentionally fail-closed with LIVE_RUNTIME_NOT_IMPLEMENTED until Task 12; ROS-free plan_only remains available and characterized.
  - Sandbox DDS socket creation emits transport warnings in the support GTest, but all nine support tests pass and no runtime graph is started.
next_command: Stage the exact Task 11 review-fix allowlist, verify the index and gates, commit the scoped fix, and do not push.
```

## Checkpoint CP-049

```yaml
checkpoint_id: CP-049
last_valid_experiment: EXP-034
current_hypothesis: NONE; Task 11 review fix round 2 is qualified at the ROS-free boundary and required no runtime experiment.
working_tree_status: HEAD f2827f825ddf15e8d346e44be5f8fe464986d2e4; the receipt-timed observer adapter, release freshness enforcement, immutable wrapper/protocol exports, three characterization-test modules, and this ledger checkpoint are dirty pending the scoped review-fix commit.
owned_processes: NONE; no ROS graph, MuJoCo, MoveIt, Gazebo, GUI, tmux, or hardware process was started.
preserved_processes: codex, kimi, and so101-py-qual remain untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - MujocoWorldObserver already stored the monotonic time at which an atomic callback was accepted, but its public snapshot discarded that value. The additive snapshot_with_receipt API now exposes it through a separate immutable ReceivedSimulationEvidence wrapper while the original SimulationEvidence schema and WorldObserver.snapshot contract remain unchanged.
  - The ROS callback captures its receipt monotonic value before message conversion, so conversion latency cannot make cached evidence appear younger.
  - ReleaseSettleExecutor requires the additive ReceiptTimedWorldObserver protocol and independently enforces PhysicalOutcomePolicy.max_observation_age_s. A cache accepted by a looser observer threshold is excluded from physical-outcome samples when older than the physical policy; fresh receipts remain successful.
  - Joint state is not added to SimulationEvidence or the receipt wrapper, so Task 5 atomic simulator evidence and non-atomic robot-state boundaries remain separated.
  - Review RED produced two behavior failures: the concrete observer could not expose callback receipt time, and four stale cached samples were retained. Evidence is /tmp/so101-debug-mujoco-migration/task-11-fix2/review-red.log with SHA-256 fc9facf1164e303c003414cddf32bca82d36dfa2a991cfa4f197b36a11580f42.
  - Callback-entry RED proved the pre-fix timestamp was captured only after conversion; evidence is /tmp/so101-debug-mujoco-migration/task-11-fix2/callback-red.log with SHA-256 0192f5820514d3fdb3797e7b4b5d5808a7269dc27a4b8c8a10070522042e774b.
  - Focused GREEN passed 34 tests; full non-live Task 11 passed 175 with two live skips. The two-package build and test passed, and aggregate colcon test-result reports 427 tests, zero errors, zero failures, and four skips.
  - Ruff check/format, provenance tests, migration isolation, diff check, and protected Gazebo tracked/status gates pass.
  - The local origin/main ref is 34 commits behind HEAD and 102 commits ahead of HEAD; its external drift was recorded only, with no fetch, rebase, merge, push, or branch mutation by this task.
disproven_routes:
  - Timestamping after snapshot completion does not represent callback receipt age and can make arbitrarily old cached evidence appear fresh.
  - Reusing the observer's configured freshness threshold is insufficient because the physical-outcome policy may intentionally be stricter.
  - Adding receipt metadata or joint state to SimulationEvidence is unnecessary; a separate immutable receipt wrapper preserves the frozen atomic evidence schema.
open_risks:
  - Live execute composition remains intentionally fail-closed with LIVE_RUNTIME_NOT_IMPLEMENTED until Task 12; ROS-free plan_only remains available and characterized.
  - Sandbox DDS socket creation emits transport warnings in the support GTest, but all nine support tests pass and no runtime graph is started.
next_command: Stage the exact Task 11 review-fix round 2 allowlist, verify the index and gates, commit the scoped fix, and do not push.
```

## Experiment EXP-035

```yaml
experiment_id: EXP-035
status: INVALID
prior_experiment: EXP-034
hypothesis: The independent full headless launch can compose MuJoCo, ros2_control, robot description and TF, MoveIt and Planning Scene, atomic observer/reset services, and the Task 12 workflow diagnostic; dry_run will obtain a nonempty arm plan without sending a controller execution goal and will then shut down only its owned stack.
prediction: The bounded diagnostic reports every required node/topic/service/action, active exact controller mapping, world-to-so101_tcp TF, planning group arm, a positive-point plan, no execute goal, advancing MuJoCo publisher sequence and simulation step, unchanged reset epoch, launch exit zero, and an empty domain after owned cleanup.
single_variable: First Task 12 live mode is dry_run with execute:=false; model, safe pose task12_safe, controller configuration, source, overlays, and readiness bounds are fixed.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus only the reviewed Task 12 dirty paths; protected Gazebo tree remains unchanged.
  - Source order is /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install and reset-qualified provenance passes.
  - Fresh ROS_DOMAIN_ID 116, GZ_PARTITION so101_mujoco_task12_exp035, task-owned tmux session so101-mujoco-exp035, and evidence root /tmp/so101-debug-mujoco-migration/exp-035/.
  - Existing codex, kimi, and so101-py-qual processes/sessions are preserved and must not be signaled or stopped.
success_criteria:
  - Readiness proves the exact node, topic, service, action, TF, planning-group, controller, Planning Scene, observer, and reset boundaries.
  - GetMotionPlan accepts task12_safe with at least one trajectory point; execute goal_sent is false and controller result is NOT_REQUESTED.
  - Atomic MuJoCo publisher_sequence and simulation_step both advance without reset-epoch change.
  - Launch exits zero, only the named owned session/PIDs are cleaned, and domain 116 is empty afterward.
failure_criteria:
  - With valid provenance, ownership, readiness, and evidence, any planning, no-execute, MuJoCo advancement, TF, or clean-shutdown assertion failure is a VALID behavioral failure and stops Task 12.
invalid_criteria:
  - Provenance mismatch, nonempty initial domain, stale install, missing ownership/process evidence, incomplete summary/log/hash/graph evidence, or polluted cleanup makes the run INVALID and it cannot support behavior.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus Task 12 dirty paths
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 116
  gz_partition: so101_mujoco_task12_exp035
commands:
  - command: ROS_DOMAIN_ID=116 GZ_PARTITION=so101_mujoco_task12_exp035 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=dry_run execute:=false simulation_session_id:=task12-exp035 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-035/summary.json
    exit_code: 1
observed:
  - Preflight domain 116 was empty, exact HEAD was 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6, the task-owned process tree was captured, and the protected Gazebo tree remained unchanged.
  - The provenance command was invoked without its mandatory --lock argument and exited 2, but the wrapper lacked errexit and incorrectly continued into launch. This violates frozen preconditions and makes all runtime behavior non-counting.
  - The launched diagnostic then rejected launch-appended --ros-args before readiness; no summary.json existed. Its process exit was 2, while the wrapper's pipeline incorrectly recorded 0, independently proving the instrumentation invalid.
  - Only so101-mujoco-exp035 was cleaned; domain 116 was empty afterward. Unrelated physical-five-success MoveIt/RViz/Gazebo PIDs 525187, 525188, 525207, 525209, 525231, and 525232 remained present and were not signaled.
inferred:
  - No planning, execution, TF, controller, or MuJoCo behavior conclusion is permitted from EXP-035.
conclusion: INVALID measurement: failed provenance precondition, non-fail-fast wrapper, missing summary, and unreliable pipeline exit capture.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-035/launch.log (sha256 25b502231b282409b038a206ac42fc544674dff4e427655557102fe1283a70e1)
  - /tmp/so101-debug-mujoco-migration/exp-035/domain-before.txt (sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-035/domain-after.txt (sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-035/process-tree.txt (sha256 a8dcb6f35b9cb08ec1e9492cf5b6e5daa2b21baddb88edbf69923b9d86869c42)
  - /tmp/so101-debug-mujoco-migration/task-12/red/ros-args-red.log (sha256 df1b89c22cb160e0dc7a6b78b0e50451aa59c9e31d982937b83679ef30a95103)
  - /tmp/so101-debug-mujoco-migration/task-12/green/ros-args-green.log (sha256 0150d14b42c4902b2b469e43e5529c434d6053054a9e809ba2e84afbc5b2994d)
decision: REPEAT with corrected preflight arguments, fail-fast wrapper, direct launch exit capture, and ROS-argument stripping; use a new ID.
next_experiment: EXP-036
```

## Experiment EXP-036

```yaml
experiment_id: EXP-036
status: VALID
prior_experiment: EXP-035
hypothesis: With the four specific EXP-035 instrumentation defects removed, the exact Task 12 source will complete the preregistered dry_run contract and produce independently checkable planning/no-execute/MuJoCo/readiness/shutdown evidence.
prediction: A fail-fast provenance preflight passes, launch exits zero directly without a pipeline, summary.json contains the complete valid dry_run contract, the opt-in live test passes, and fresh domain 117 is empty before and after.
single_variable: Measurement validity only: correct --lock provenance invocation, fail-fast wrapper, direct launch exit code, and the TDD-qualified stripping of launch-appended ROS arguments. Runtime mode, task12_safe pose, model, controllers, overlays, and acceptance contract are unchanged from EXP-035.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus the same Task 12 dirty paths, including ROS-argument RED/GREEN; protected Gazebo tree unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; check_reset_qualified_runtime.py --lock config/dependency-lock.yaml --check-only exits zero under errexit.
  - Fresh ROS_DOMAIN_ID 117, GZ_PARTITION so101_mujoco_task12_exp036, task-owned session so101-mujoco-exp036, evidence root /tmp/so101-debug-mujoco-migration/exp-036/.
  - Existing codex, kimi, so101-py-qual, and independently observed physical-five-success processes remain preserved and untouched.
success_criteria:
  - Same dry_run readiness, planning, no-controller-execution, MuJoCo advancement, unchanged reset epoch, and clean shutdown criteria frozen in EXP-035.
  - Summary validator passes only after direct launch exit zero and an independently empty post-launch domain are supplied.
failure_criteria:
  - With all preconditions valid, any contract assertion failure is a VALID behavioral failure and stops Task 12 without guessing or starting execute.
invalid_criteria:
  - Any provenance, initial-domain, install, ownership, summary, graph, hash, exit-code, or cleanup defect remains INVALID and cannot support behavior.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus Task 12 dirty paths
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 117
  gz_partition: so101_mujoco_task12_exp036
commands:
  - command: ROS_DOMAIN_ID=117 GZ_PARTITION=so101_mujoco_task12_exp036 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=dry_run execute:=false simulation_session_id:=task12-exp036 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-036/summary.json
    exit_code: 0
observed:
  - All frozen preconditions passed: domain 117 was empty, reset-qualified runtime provenance SHA-256 was b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1, exact HEAD was 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus the declared Task 12 paths, and ownership/process evidence was complete.
  - The full graph reached readiness before planning: three controllers configured and activated, atomic MuJoCo evidence and reset services were available, MoveIt loaded OMPL and both FollowJointTrajectory controller mappings, Planning Scene published, and the planning service accepted the request.
  - OMPL constructed an arm RRTConnect planning context, but AddTimeOptimalParameterization reported no acceleration limit for joint 1 and failed the PlanningResponseAdapter. The service returned MOVEIT_PLAN_FAILED; the diagnostic node exited 1 and summary.json recorded that exact failure.
  - The launch supervisor completed its requested shutdown with wrapper exit zero, domain 117 was empty afterward, and only so101-mujoco-exp036 was cleaned. The unrelated physical-five-success MoveIt/RViz/Gazebo processes observed before the run remained after it and were not signaled.
  - Because planning failed, no dry_run success can be claimed and EXP-037 execute was not registered or started.
inferred:
  - The first bad behavioral boundary is MoveIt response time parameterization, not ROS graph readiness, controller activation, TF, Planning Scene startup, MuJoCo evidence availability, or OMPL pipeline loading.
conclusion: VALID behavioral failure: the required dry_run planning proof failed because the composed robot planning configuration has no acceleration limit for joint 1 (and therefore cannot pass AddTimeOptimalParameterization).
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-036/launch.log (sha256 836d6199a2d6ae9870320e219ab863643e8ec3b918d3fb73d38a41e1cd9a08bb)
  - /tmp/so101-debug-mujoco-migration/exp-036/summary.json (sha256 24579a7f3760bbcdf39087680e897ad9d436a7abf0875e39ef7329d83f9bcc2b)
  - /tmp/so101-debug-mujoco-migration/exp-036/graph-live.txt (sha256 57298d3bcc79b168e00bf6732617d232b3ee0954d691a3607eb90d5350990a3a)
  - /tmp/so101-debug-mujoco-migration/exp-036/domain-before.txt (sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-036/domain-after.txt (sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-036/process-tree.txt (sha256 8188497e636c47978894cbefc3611f22b11095efb477c758cd175a034e7a90b6)
  - /tmp/so101-debug-mujoco-migration/exp-036/processes-before.txt (sha256 205d3ce83144507c1884ebd2f750806ca2feb6c7a4ab27befc0b5912a5be405d)
  - /tmp/so101-debug-mujoco-migration/exp-036/processes-after.txt (sha256 dae2f24e991cc2b2cc3a178ae308571b0ca8550efc38416c7a5e94086a643816)
  - /tmp/so101-debug-mujoco-migration/exp-036/provenance.txt (sha256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1)
decision: ABANDON Task 12 at the mandated valid-failure stop. Do not alter limits, register EXP-037, execute motion, run final success gates, or commit.
next_experiment: NONE
```

## Checkpoint CP-050

```yaml
checkpoint_id: CP-050
last_valid_experiment: EXP-036
current_hypothesis: The full headless stack reaches the MoveIt planning response boundary, but the owned planning configuration lacks acceleration limits required by AddTimeOptimalParameterization.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; only Task 12 independent-package config, launch, headless diagnostic, tests, provenance, package metadata, ledger, and report paths are dirty or untracked; protected Gazebo diff/status remain zero.
owned_processes: NONE; so101-mujoco-exp035 and so101-mujoco-exp036 are absent, and domains 116 and 117 are empty.
preserved_processes: codex, kimi, so101-py-qual, and the independently observed physical-five-success MoveIt/RViz/Gazebo processes remain untouched.
confirmed_conclusions:
  - Initial launch contract RED failed on the missing headless module (exit 2); focused GREEN passed 7 plus one live skip.
  - ROS-argument RED failed on the missing stripping boundary (exit 2); GREEN passed 8 plus one live skip.
  - Pre-live two-package build passed, Ruff passed, installed launch/executables resolved to the project overlay, and non-live tests passed 182 with three skips.
  - EXP-035 is INVALID because its provenance/instrumentation preconditions failed; it supports no behavior conclusion.
  - EXP-036 is a VALID behavioral failure after complete provenance, readiness, ownership, graph, and cleanup evidence. The first bad boundary is AddTimeOptimalParameterization rejecting absent joint acceleration limits.
disproven_routes:
  - The Task 12 dry-run failure is not caused by absent MuJoCo services/evidence, inactive controllers, missing Planning Scene, unavailable trajectory actions, missing TF, or an unloaded OMPL pipeline; all preceded the failure successfully in EXP-036.
open_risks:
  - No successful Task 12 dry-run exists, so no execute run was authorized or attempted and no joint convergence or executed MuJoCo movement claim is available.
  - Launch shutdown after the diagnostic failure logged a move_group exit -11 even though domain cleanup completed; this remains unqualified and is secondary to the first planning failure.
  - Task 12 changes are intentionally uncommitted because the success contract failed.
next_command: NONE; user direction is required before changing any planning limit or registering a new experiment.
```

## Checkpoint CP-051

```yaml
checkpoint_id: CP-051
last_valid_experiment: EXP-036
current_hypothesis: Restoring the exact frozen joint dynamics configuration omitted by Task 12 will let the already-reached MoveIt response adapter time-parameterize task12_safe.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; the existing Task 12 dirty state is preserved and now additionally contains the focused joint-limit regression, independent config, launch injection, and provenance correction.
owned_processes: NONE; no live process was started during the authorized correction and prior task-owned sessions remain absent.
preserved_processes: codex, kimi, so101-py-qual, and independently observed physical-five-success processes remain untouched.
confirmed_conclusions:
  - User direction explicitly resumed the full goal after CP-050 and authorized one correction round without reset, stash, or clean.
  - Frozen behavior source 8d7913e7f552a40ee627d65be8b873ac16748bc9 defines exact joints 1 through 6 max_velocity 10.0, max_acceleration 5.0, and default velocity/acceleration scaling 0.1; source SHA-256 is 210bb4792821bf081df092b11edc398050b1140cbef5c6f8f139687e87148973.
  - Behavior-level RED failed because moveit_parameters lacked robot_description_planning; RED log SHA-256 is 3f04c90de2427eeec18c0ff9e0fce3566ec3ea2c712e1b8559365829378e9c3f.
  - The independent config now matches that frozen source byte-for-byte and focused GREEN passed nine tests with one opt-in live skip; GREEN log SHA-256 is d070d4fa1ac6f0f5656bb7a5216bdd3658f870e5b02442b3af232b8c90a60ad2.
disproven_routes:
  - Inventing or tuning a new acceleration threshold is unnecessary; the omitted contract already exists in the sole allowed behavior source.
open_risks:
  - The correction has not yet been exercised in a fresh live domain.
next_command: Run the preregistered EXP-037 dry_run only after all offline, provenance, ownership, and fresh-domain preconditions pass.
```

## Experiment EXP-037

```yaml
experiment_id: EXP-037
status: VALID
prior_experiment: EXP-036
hypothesis: Injecting the exact frozen six-joint dynamics limits into robot_description_planning will let the otherwise unchanged full headless stack time-parameterize and accept a task12_safe arm plan without execution.
prediction: The reset-qualified full stack reaches the same readiness boundary as EXP-036, planning returns at least one trajectory point without an AddTimeOptimalParameterization error, no controller goal is sent, MuJoCo publisher sequence and simulation step advance with unchanged reset epoch, launch exits zero, and the fresh domain is empty afterward.
single_variable: The only behavioral change from EXP-036 is the exact byte-matching frozen joint_limits.yaml and its robot_description_planning injection; run mode remains dry_run, execute remains false, and model, safe pose, controllers, overlays, timeouts, and evidence validator are unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus only the declared Task 12 dirty paths; protected Gazebo tree remains unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; reset-qualified runtime provenance check passes with the frozen lock.
  - Fresh confirmed-empty ROS_DOMAIN_ID 118, GZ_PARTITION so101_mujoco_task12_exp037, task-owned tmux session so101-mujoco-exp037, and evidence root /tmp/so101-debug-mujoco-migration/exp-037/.
  - Existing codex, kimi, so101-py-qual, and independently observed physical-five-success processes/sessions are preserved and must not be signaled or stopped.
success_criteria:
  - Readiness independently proves required nodes, topics, services, actions, active exact controller mapping, world-to-so101_tcp TF, planning group arm, Planning Scene, observer, and reset boundaries.
  - GetMotionPlan accepts task12_safe with at least one trajectory point; execution goal_sent is false and controller result is NOT_REQUESTED.
  - Atomic MuJoCo publisher_sequence and simulation_step both advance without reset-epoch change.
  - Direct launch exit is zero, only the named task-owned session/PIDs are cleaned, and domain 118 is empty afterward.
failure_criteria:
  - With valid provenance, fresh-domain, ownership, readiness, evidence, graph, and cleanup preconditions, any planning, no-execute, MuJoCo advancement, or shutdown assertion failure is a VALID behavioral failure and stops Task 12 without guessing or registering execute.
invalid_criteria:
  - Any provenance mismatch, nonempty initial domain, stale install, ownership defect, incomplete summary/log/hash/graph evidence, unreliable exit capture, or polluted cleanup makes the run INVALID and supports no behavior conclusion.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus the declared Task 12 dirty paths and frozen joint-limit correction
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  behavior_source_joint_limits_sha256: 210bb4792821bf081df092b11edc398050b1140cbef5c6f8f139687e87148973
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 118
  gz_partition: so101_mujoco_task12_exp037
commands:
  - command: ROS_DOMAIN_ID=118 GZ_PARTITION=so101_mujoco_task12_exp037 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=dry_run execute:=false simulation_session_id:=task12-exp037 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-037/summary.json
    exit_code: 0
observed:
  - All preconditions passed: domain 118 was empty, exact HEAD was 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 paths, protected Gazebo tracked/status gates were zero, the installed frozen config was rebuilt, reset-qualified provenance SHA-256 was b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1, and the owned session name was free.
  - The runtime started MuJoCo, robot_state_publisher, MoveIt, controller manager, all three spawners, and the diagnostic. The required graph boundary became visible as soon as the arm trajectory action and planning boundaries existed.
  - The diagnostic then called ListControllers once. Its response contained arm_controller and joint_state_broadcaster as active but did not yet contain gripper_controller; it immediately raised `RuntimeError: controllers are not active` instead of waiting within the remaining 30-second readiness deadline.
  - The launch supervisor performed owned shutdown and returned zero, while summary.json preserved the diagnostic failure. No plan was attempted, so the frozen joint-limit correction did not reach time parameterization and no execution run was authorized.
  - The owned so101-mujoco-exp037 session was removed, domain 118 was independently empty afterward, and codex, kimi, and so101-py-qual remained present and untouched. The earlier physical-five-success processes were already absent in the preregistered before snapshot and were not part of this experiment.
inferred:
  - The first bad boundary is a controller-readiness race in the Task 12 diagnostic: graph readiness can complete after the arm action appears but before the concurrently spawned gripper controller is listed active, and controller state is not polled to the deadline.
  - EXP-037 cannot support any conclusion about the joint-limit planning correction because planning was never invoked.
conclusion: VALID behavioral failure: the required full-launch readiness contract is nondeterministic because the diagnostic samples controller state once instead of waiting for every required controller to become active.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-037/launch.log (sha256 fdbb16ecf5db6371d567a47cc57cac00877d16af9a3170f8c186627b4cf9b8c5)
  - /tmp/so101-debug-mujoco-migration/exp-037/summary.json (sha256 4ef1fa8132706e7e38ee210e53d02b76f02a4a6672bfa6c29e50db3710dbd446)
  - /tmp/so101-debug-mujoco-migration/exp-037/process-tree.txt (sha256 8d3a71df0732eddf2ec2f03e0835c096a89428ead5eede211f28fa16344a14e2)
  - /tmp/so101-debug-mujoco-migration/exp-037/domain-before.txt (sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-037/domain-after.txt (sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-037/provenance.txt (sha256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1)
  - /tmp/so101-debug-mujoco-migration/exp-037/hashes.txt
decision: ABANDON Task 12 at the mandated valid-failure stop. Do not rerun to mask the race, change readiness behavior, register execute, run final success gates, or commit without new user direction.
next_experiment: NONE
```

## Checkpoint CP-052

```yaml
checkpoint_id: CP-052
last_valid_experiment: EXP-037
current_hypothesis: The Task 12 full launch has a controller-readiness race because it waits for graph boundaries but samples ListControllers only once before all concurrent spawners necessarily finish.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; only Task 12 independent-package config, launch, headless diagnostic, tests, provenance, package metadata, ledger, and ignored report paths are dirty or untracked; protected Gazebo diff/status remain zero.
owned_processes: NONE; so101-mujoco-exp037 is absent and domain 118 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched; the earlier physical-five-success processes were already absent before EXP-037.
confirmed_conclusions:
  - Joint-limit correction TDD is exact: behavior RED failed on missing robot_description_planning, focused GREEN passed nine with one opt-in skip, and the independent config SHA matches frozen source SHA 210bb4792821bf081df092b11edc398050b1140cbef5c6f8f139687e87148973.
  - Ruff passed and the two-package build passed with the independent joint_limits.yaml installed. Package pytest has 183 passes and three opt-in skips; its single failure is the expected nonterminal ledger-state assertion while an experiment was registered.
  - EXP-037 passed provenance, source, isolation, fresh-domain, ownership, and cleanup preconditions but failed before planning when the one-shot controller-state response omitted the still-spawning gripper controller.
  - No execute experiment was registered or started; no hardware, GUI, grasp, threshold, Gazebo-tree, unrelated-session, push, merge, reset, stash, or clean action occurred.
disproven_routes:
  - A single ListControllers response after generic graph readiness does not prove every required controller is active under concurrent spawner startup.
  - Repeating the same run until the race happens to pass would not qualify the deterministic full-launch readiness contract.
open_risks:
  - The frozen joint-limit correction remains live-unqualified because EXP-037 never reached planning.
  - No successful Task 12 dry_run or execute evidence exists, so plan acceptance, controller execution, joint convergence, and executed MuJoCo movement cannot be claimed.
  - Shutdown after the diagnostic failure again logged move_group exit -11; it remains secondary to the first readiness failure.
next_command: NONE; user direction is required before adding a controller-readiness polling correction or registering another experiment.
```

## Checkpoint CP-053

```yaml
checkpoint_id: CP-053
last_valid_experiment: EXP-037
current_hypothesis: Polling exact required controller names and active states only until the existing overall readiness deadline will make concurrent spawner startup deterministic without changing any timeout or planning behavior.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; the preserved Task 12 dirty state additionally contains only readiness behavior tests and the bounded production poll.
owned_processes: NONE; no live process was started during fix round 2.
preserved_processes: codex, kimi, and so101-py-qual remain untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - User direction explicitly resumed the persistent Task 12 goal after CP-052 and authorized readiness fix round 2 without reset, stash, or clean.
  - Executable controlled-sequence RED produced three failures because the current implementation had no polling boundary; RED SHA-256 is b3f39098d4005cb61d4536c458e4b899d1c524851a18fbf9ab3e62e4ee902abd.
  - Minimal GREEN repeatedly consumes ListControllers responses until every exact required controller is active or the unchanged overall deadline expires; missing, inactive, or otherwise unexpected required states do not count. Focused result is 12 passed plus one opt-in live skip; GREEN SHA-256 is 170f4642aaeddc36e92eada7bcf91f9f2591215a656254e9e5e6f47fcdbb8000.
disproven_routes:
  - Extending the readiness timeout or adding a guessed startup sleep is unnecessary; the existing deadline already bounds service polling.
open_risks:
  - The correction has not yet been exercised against concurrent live spawners, and the frozen joint-limit correction has still not reached live planning.
next_command: Run the preregistered EXP-038 dry_run only after offline, provenance, ownership, and fresh-domain preconditions pass.
```

## Experiment EXP-038

```yaml
experiment_id: EXP-038
status: VALID
prior_experiment: EXP-037
hypothesis: With exact required-controller polling bounded by the unchanged overall readiness deadline, the full headless stack will pass concurrent startup and the restored frozen joint dynamics contract will let task12_safe plan successfully without execution.
prediction: All three required controllers become active within the existing deadline, readiness and the full graph pass, planning returns at least one trajectory point without time-parameterization failure, no execution goal is sent, MuJoCo publisher sequence and simulation step advance with unchanged reset epoch, launch exits zero, and the fresh domain is empty afterward.
single_variable: The only change from EXP-037 is bounded repeated ListControllers sampling for exact required active states; readiness_timeout_s remains 30.0 and joint limits, model, safe pose, controllers, overlays, dry_run mode, and acceptance thresholds are unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus only declared Task 12 dirty paths; protected Gazebo tree remains unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; reset-qualified runtime provenance passes with the frozen lock.
  - Fresh confirmed-empty ROS_DOMAIN_ID 119, GZ_PARTITION so101_mujoco_task12_exp038, task-owned tmux session so101-mujoco-exp038, and evidence root /tmp/so101-debug-mujoco-migration/exp-038/.
  - Existing codex, kimi, and so101-py-qual processes/sessions are preserved and must not be signaled or stopped.
success_criteria:
  - Readiness proves required nodes, topics, services, actions, active exact controller mapping, world-to-so101_tcp TF, planning group arm, Planning Scene, observer, and reset boundaries.
  - GetMotionPlan accepts task12_safe with at least one trajectory point; execution goal_sent is false and controller result is NOT_REQUESTED.
  - Atomic MuJoCo publisher_sequence and simulation_step both advance without reset-epoch change.
  - Direct launch exit is zero, only the named owned session/PIDs are cleaned, and domain 119 is empty afterward.
failure_criteria:
  - With valid provenance, source, fresh-domain, ownership, evidence, and cleanup, any readiness, planning, no-execute, MuJoCo advancement, or shutdown contract failure is a VALID behavioral failure and stops Task 12 without guessing or registering execute.
invalid_criteria:
  - Provenance mismatch, nonempty initial domain, stale install, ownership defect, incomplete summary/log/hash/process evidence, unreliable exit capture, or polluted cleanup makes the run INVALID and supports no behavior conclusion.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and readiness fix round 2
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 119
  gz_partition: so101_mujoco_task12_exp038
commands:
  - command: ROS_DOMAIN_ID=119 GZ_PARTITION=so101_mujoco_task12_exp038 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=dry_run execute:=false simulation_session_id:=task12-exp038 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-038/summary.json
    exit_code: 0
observed:
  - All preconditions passed: fresh domain 119 was empty, exact HEAD and declared dirty scope were captured, reset-qualified provenance SHA-256 was b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1, the installed overlay was rebuilt, protected Gazebo gates were zero, and owned/preserved sessions were recorded.
  - The live graph contained controller manager, MuJoCo ros2_control, robot_state_publisher, move_group, arm controller, diagnostic, and TF helper nodes while the owned launch was running.
  - Readiness waited through concurrent startup and summary evidence recorded arm_controller, gripper_controller, and joint_state_broadcaster all active with their exact joint mapping, required graph boundaries, world-to-so101_tcp TF, and planning group arm.
  - The restored frozen limits reached MoveIt: task12_safe planning was accepted with 47 trajectory points; execution goal_sent was false, succeeded was false, and controller result was NOT_REQUESTED.
  - Atomic MuJoCo publisher_sequence and simulation_step each advanced by 1 with reset epoch unchanged at 0. Launch exit was zero, live summary validation passed one test, only the owned session was removed, and domain 119 was empty afterward.
inferred:
  - Bounded exact-controller polling removes the EXP-037 startup race without extending the existing deadline.
  - Frozen joint dynamics injection resolves the EXP-036 time-parameterization failure for the non-executing safe plan.
conclusion: VALID success: the full headless dry_run independently proves readiness, planning, no controller execution, advancing MuJoCo evidence, unchanged reset epoch, and clean owned shutdown.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-038/launch.log (sha256 e479863bb4990a8c37ec136f514f0db234931c2cd51632858281c2d057d88dcc)
  - /tmp/so101-debug-mujoco-migration/exp-038/summary-final.json (sha256 68fe89b6615b84832e98b160886393ac6c111aca4a08d570c54162998ade1011)
  - /tmp/so101-debug-mujoco-migration/exp-038/graph-live.txt (sha256 a248f93a82c75bb40767a9d75d9532d68784e6835e898a0a722a45caf416e7b6)
  - /tmp/so101-debug-mujoco-migration/exp-038/process-tree.txt (sha256 8b2b508f49c276ee02be96a02b1dffd1add2364971bc183849750d1bdd5e752a)
  - /tmp/so101-debug-mujoco-migration/exp-038/live-validator.log (sha256 57e483a5ab24700c87774df1edfdab1c89dfaf089ba40715ea705e2c323836ac)
  - /tmp/so101-debug-mujoco-migration/exp-038/domain-before.txt and domain-after.txt (each sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-038/provenance.txt (sha256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1)
decision: ACCEPT dry_run evidence and preregister one separate non-grasp execute on a new domain; do not reuse this runtime.
next_experiment: EXP-039
```

## Checkpoint CP-054

```yaml
checkpoint_id: CP-054
last_valid_experiment: EXP-038
current_hypothesis: The same fixed full stack can execute task12_safe once, with the five arm joints converging to their named target and joint 6 independently remaining at its captured non-grasp hold target.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; only declared Task 12 implementation/config/test/provenance/package/ledger/report paths remain dirty or untracked.
owned_processes: NONE; so101-mujoco-exp038 is absent and domain 119 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched.
confirmed_conclusions:
  - EXP-038 is a valid dry_run success with 47 planned points, no controller goal, all required active controller states, positive atomic publisher/step deltas, unchanged reset epoch, and clean shutdown.
  - Reset-qualified provenance and protected Gazebo gates remained valid before the run.
disproven_routes:
  - The EXP-036 missing-limit failure and EXP-037 controller-startup race no longer occur in the qualified dry_run.
open_risks:
  - No execution, arm convergence, joint-6 hold convergence, or executed MuJoCo movement proof exists yet.
next_command: Run preregistered EXP-039 only after its fresh-domain, exact-source, provenance, ownership, and independent six-joint evidence capture preconditions pass.
```

## Experiment EXP-039

```yaml
experiment_id: EXP-039
status: VALID
prior_experiment: EXP-038
hypothesis: The exact EXP-038 stack can explicitly execute the non-grasp task12_safe trajectory, converge arm joints 1 through 5 to their configured target while joint 6 holds its captured initial target, produce advancing atomic MuJoCo motion evidence, and cleanly stop only its owned runtime.
prediction: Planning is accepted with positive trajectory points, MoveIt/controller execution succeeds, joints 1 through 5 finish within 0.01 rad of [0.0, 0.1, 0.1, 0.2, 0.0], independent joint-state stream shows joint 6 final within 0.01 rad of its initial non-grasp hold value, maximum arm motion exceeds 0.05 rad, MuJoCo publisher_sequence and simulation_step advance with unchanged reset epoch, launch exits zero, and the fresh domain ends empty.
single_variable: Explicit run_mode execute with execute true; source, model, controller configuration, safe pose, fixed frozen limits, readiness deadline, convergence/motion thresholds, overlays, and headless runtime are unchanged from successful EXP-038.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus only declared Task 12 dirty paths; protected Gazebo tree unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; reset-qualified provenance passes with the frozen lock.
  - Fresh confirmed-empty ROS_DOMAIN_ID 120, GZ_PARTITION so101_mujoco_task12_exp039, task-owned tmux session so101-mujoco-exp039, and evidence root /tmp/so101-debug-mujoco-migration/exp-039/.
  - A task-owned joint-state evidence subscriber records the first and final complete six-joint samples in the same domain; it commands nothing and is cleaned with the owned session.
  - Existing codex, kimi, and so101-py-qual processes/sessions are preserved and must not be signaled or stopped.
success_criteria:
  - Readiness and planning satisfy EXP-038's exact graph/controller/TF/Planning Scene/observer/reset contract.
  - Plan contains positive trajectory points, explicit execution goal is sent, MoveIt/controller result is SUCCEEDED, and summary proves joints 1 through 5 converged with maximum target error at most 0.01 rad and maximum motion greater than 0.05 rad.
  - Independent complete joint-state samples prove joint 6 remains within 0.01 rad of its initial non-grasp hold target, completing six-joint convergence evidence.
  - Atomic MuJoCo publisher_sequence and simulation_step advance, reset epoch is unchanged, launch exit is zero, only named owned processes are cleaned, and domain 120 is empty afterward.
failure_criteria:
  - With valid preconditions, any readiness, planning, execution, controller result, six-joint convergence, MuJoCo movement, reset-epoch, or clean-shutdown assertion failure is a VALID behavioral failure and stops Task 12.
invalid_criteria:
  - Provenance mismatch, nonempty initial domain, stale install, missing/invalid six-joint stream, ownership defect, incomplete summary/log/hash/process evidence, unreliable exit capture, or polluted cleanup makes the run INVALID and supports no behavior conclusion.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths qualified by EXP-038
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 120
  gz_partition: so101_mujoco_task12_exp039
commands:
  - command: ROS_DOMAIN_ID=120 GZ_PARTITION=so101_mujoco_task12_exp039 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=execute execute:=true simulation_session_id:=task12-exp039 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-039/summary.json
    exit_code: 0
observed:
  - Preconditions passed: domain 120 was empty, exact HEAD/dirty scope and protected Gazebo gates were valid, reset-qualified provenance SHA-256 was b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1, and only the task-owned launch plus read-only joint-state subscriber were started.
  - Live graph and process evidence captured controller manager, MoveIt, MuJoCo ros2_control, robot_state_publisher, controllers, diagnostic, and the task-owned joint-state subscriber.
  - Readiness completed with the bounded controller poll. MoveIt accepted planning and completed AddTimeOptimalParameterization, ValidateSolution, and DisplayMotionPath before receiving the explicit execution request.
  - TrajectoryExecutionManager rejected the handoff before sending a controller trajectory: `Invalid Trajectory: start point deviates from current robot state more than 0.01 at joint '2'`. The execution action completed ABORTED and the diagnostic summary recorded `execution failed: MOVEIT_EXECUTION_FAILED`.
  - The independent stream contains 147 complete ordered six-joint samples with no subscriber error. Joint 6 remained within 0.0023626745226074733 rad of its initial non-grasp hold target, but arm execution/convergence cannot be claimed because controller handoff was rejected.
  - Launch supervisor exit was zero after diagnostic-directed shutdown. Only so101-mujoco-exp039 and its evidence window were removed, domain 120 was empty afterward, and codex, kimi, and so101-py-qual remained untouched.
inferred:
  - The first bad execute boundary is MoveIt's frozen start-state tolerance validation between planning-state capture and controller handoff, not readiness, planning, time parameterization, or joint-6 hold evidence.
  - No controller execution, five-arm-joint convergence, or executed MuJoCo movement success is supported by EXP-039.
conclusion: VALID behavioral failure: the explicit non-grasp execute request was aborted because joint 2 drifted more than the unchanged 0.01 start tolerance before trajectory execution.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-039/launch.log (sha256 cfea801064418c8e359af944834702e173734c8f507a5ee8fb5c1fcdb4b4cb64)
  - /tmp/so101-debug-mujoco-migration/exp-039/summary.json (sha256 78acfc7676e1f970a08d0891d5b060eea423ce036931a4f2c8d5e54dda73ab94)
  - /tmp/so101-debug-mujoco-migration/exp-039/graph-live.txt (sha256 9eeffff2a899d86d056a937d2f5e88e016d9bf451b4758d3c23e6b778f6f9425)
  - /tmp/so101-debug-mujoco-migration/exp-039/process-tree.txt (sha256 66eaa06e61b3f37aa545a7ff1b6a0642a5ae71da127832cf10185b9360babf48)
  - /tmp/so101-debug-mujoco-migration/exp-039/joint-states.yaml (sha256 b73051d5428c604ed08c3863356380b7e801df9c9efa26dc98ee998a4e131cd4)
  - /tmp/so101-debug-mujoco-migration/exp-039/joint-evidence-summary.json (sha256 c7e395a8e269969e853542457e71e0945794e0033b299e18ba2f0cef30356ea6)
  - /tmp/so101-debug-mujoco-migration/exp-039/domain-before.txt and domain-after.txt (each sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-039/provenance.txt (sha256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1)
decision: ABANDON Task 12 at the mandated valid-failure stop. Do not adjust the 0.01 tolerance, modify planning/execution, rerun, run final success gates, stage, or commit without new user direction.
next_experiment: NONE
```

## Checkpoint CP-055

```yaml
checkpoint_id: CP-055
last_valid_experiment: EXP-039
current_hypothesis: Joint 2 can drift farther than MoveIt's unchanged 0.01 allowed_start_tolerance between current-state capture and explicit trajectory handoff.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; only Task 12 independent-package config, launch, diagnostic, tests, provenance, package metadata, ledger, and ignored report paths are dirty or untracked; protected Gazebo tracked/status gates remain zero.
owned_processes: NONE; so101-mujoco-exp038 and so101-mujoco-exp039 are absent, and domains 119 and 120 are empty.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - Readiness fix round 2 has executable RED/GREEN coverage for delayed concurrent activation, never-active timeout, and rejection of non-active required states, all under the unchanged overall deadline.
  - Ruff check/format and the two-package build pass. Focused contract/Ruff gates pass 16 plus one opt-in skip; the full package run before formatting reported 185 passes and three skips with only the formatting gate and truthful in-progress-ledger assertion failing, and formatting is now corrected.
  - EXP-038 validly proves full readiness, 47-point safe planning, no execution, positive atomic MuJoCo deltas, unchanged reset epoch, and clean owned shutdown.
  - EXP-039 validly proves readiness and planning reached explicit execution, then failed at MoveIt's unchanged start-state tolerance for joint 2 before controller trajectory execution. The independent six-joint stream is valid, but execution/convergence/movement success is absent.
  - No hardware, GUI, grasp, threshold change, Gazebo-tree modification, unrelated-session signal, push, merge, reset, stash, or clean action occurred.
disproven_routes:
  - Controller readiness polling and frozen joint limits are insufficient by themselves to qualify execute when the planning start state drifts before handoff.
  - Rerunning or widening the 0.01 start tolerance would violate the preregistered stop and no-threshold-change rules.
open_risks:
  - Task 12 lacks successful controller execution, five-arm-joint target convergence, and executed MuJoCo movement proof.
  - Launch-directed failure teardown continues to log move_group exit -11 as a secondary unqualified shutdown issue.
next_command: NONE; user direction is required before any new planning/execution behavior correction or experiment.
```

## Checkpoint CP-056

```yaml
checkpoint_id: CP-056
last_valid_experiment: EXP-039
current_hypothesis: Joint 2 either already differs from the returned trajectory first point at plan response or accumulates the rejecting deviation between plan response and ExecuteTrajectory handoff.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; current Task 12 dirty state preserved without reset, stash, or clean; no production behavior correction has been made after CP-055.
owned_processes: NONE; prior task-owned sessions are absent and domains 119/120 are empty.
preserved_processes: codex, kimi, and so101-py-qual remain untouched.
confirmed_conclusions:
  - EXP-039 launch log timestamps planning request at 1786368114.054992233, returned adapters through 1786368114.076488838, execution request at 1786368114.084640160, and rejection at 1786368114.086281582.
  - EXP-039 summary contains only the terminal MOVEIT_EXECUTION_FAILED error. Its external six-joint stream has simulation stamps and complete values, but not local receipt timestamps correlated to plan request, plan response, or immediate pre-execute.
  - The current ordering is complete joint sample -> GetMotionPlan -> trajectory extraction -> ExecuteTrajectory, with no explicit spin between plan response and execute call; however, exact first-point positions and exact latest samples at those boundaries were not serialized.
disproven_routes:
  - EXP-039's first/last external joint samples cannot prove whether the 0.01 deviation existed at plan response or accumulated afterward.
open_risks:
  - Measurement logging itself must not add a spin, sleep, timeout, planning, tolerance, controller, or motion change.
next_command: Run the preregistered measurement-only EXP-040 once after adding structured boundary observability and passing source/provenance/ownership/fresh-domain preconditions.
```

## Experiment EXP-040

```yaml
experiment_id: EXP-040
status: VALID
prior_experiment: EXP-039
hypothesis: Boundary-correlated measurements will show whether the returned trajectory first point already deviates from the latest finite complete joint state at plan response, or whether a greater-than-0.01 deviation accumulates before ExecuteTrajectory.
prediction: Structured evidence records exact trajectory joint names/first-point positions, complete finite joint samples with message simulation stamp and local receipt monotonic time at plan request, plan response, and immediately pre-execute, plus controller states and atomic MuJoCo simulation_time/publisher_sequence/simulation_step/reset_epoch/session tuple. Per-joint deltas and boundary time deltas then identify the first crossing of 0.01 without changing execution semantics.
single_variable: Measurement observability only; the exact EXP-039 config, code ordering, execute call, model, controllers, safe pose, frozen 0.01 start tolerance, thresholds, readiness timeout, planning limits, source order, and motion remain unchanged. Measurement adds no spin, sleep, wait, service/action call, or state mutation.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and measurement-only structured logging; protected Gazebo tree unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; reset-qualified provenance passes with the frozen lock.
  - Fresh confirmed-empty ROS_DOMAIN_ID 121, GZ_PARTITION so101_mujoco_task12_exp040, task-owned tmux session so101-mujoco-exp040, evidence root /tmp/so101-debug-mujoco-migration/exp-040/.
  - Existing codex, kimi, and so101-py-qual processes/sessions are preserved and must not be signaled or stopped.
success_criteria:
  - All three named boundary records contain finite ordered joint samples, local receipt/sample monotonic values, simulation stamps, controller states, and atomic evidence tuple; plan response contains exact trajectory first point and names.
  - The one unchanged execute diagnostic reaches a terminal underlying success or failure with direct launch exit capture, complete logs/hashes/process evidence, owned cleanup, and empty domain 121.
  - VALID measurement semantics are independent of the underlying behavior: execution success is recorded as behavioral success; the same or another contract failure is recorded as behavioral failure, provided all measurement/precondition evidence remains valid.
failure_criteria:
  - A complete valid measurement whose unchanged run fails readiness, planning, execution, convergence, MuJoCo movement, reset epoch, or shutdown is a VALID behavioral failure and is terminalized without a production fix.
invalid_criteria:
  - Missing/malformed boundary record, instrumentation that changes call ordering or adds runtime waits/calls, provenance mismatch, nonempty initial domain, stale install, ownership defect, incomplete summary/log/hash/process evidence, unreliable exit capture, or polluted cleanup makes EXP-040 INVALID and supports no causal conclusion.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and measurement-only observability
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 121
  gz_partition: so101_mujoco_task12_exp040
commands:
  - command: ROS_DOMAIN_ID=121 GZ_PARTITION=so101_mujoco_task12_exp040 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=execute execute:=true simulation_session_id:=task12-exp040 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-040/summary.json
    exit_code: 0
observed:
  - All frozen preconditions passed: domain 121 was empty, exact HEAD and dirty scope were captured, reset-qualified provenance SHA-256 was b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1, protected Gazebo gates were zero, and only the named owned session was started.
  - Plan-request boundary monotonic time was 2692557.461306925. Its latest complete finite joint sample was received at 2692557.455336982 with simulation stamp 1.734 s and positions [-0.0016580672244613085, 0.6637178770200481, 0.26929049715874454, 0.05754074285101374, 0.00009117452787544724, -0.003487822006456804]. Atomic evidence was session task12-exp040, simulation time 1.738 s, publisher sequence/step 167/167, reset epoch 0; all three required controllers were active.
  - Plan-response boundary monotonic time was 2692557.757419311. The returned first point for joints 1 through 5 exactly equaled the plan-request sample, with zero per-joint delta and time_from_start zero. The latest joint sample was received at 2692557.753158297 with simulation stamp 2.016 s and positions [-0.00013910291309458155, 1.3508556799055613, 0.3710563485655239, 0.07926001452117376, 0.00009731322268405661, -0.002300061280728079].
  - From trajectory first point to plan-response sample, deltas in radians were joint 1 +0.001518964311366727, joint 2 +0.6871378028855132, joint 3 +0.10176585140677935, joint 4 +0.021719271670160023, and joint 5 +0.000006138694808609371. Planning-boundary elapsed time was 0.29611238604411483 s, joint-receipt elapsed time 0.29782131500542164 s, simulation time advanced 0.2719999999999998 s, and atomic sequence/step advanced 27/27 with no reset.
  - Immediate pre-execute boundary monotonic time was 2692557.757545859, only 0.00012654811143875122 s after plan response. Its joint sample, sample receipt, simulation stamp, atomic tuple, controller states, and trajectory first point were byte-for-value identical to plan response; every response-to-pre-execute joint/sequence/step/reset delta was zero.
  - The unchanged execution again failed `Invalid Trajectory: start point deviates from current robot state more than 0.01 at joint '2'` and summary recorded MOVEIT_EXECUTION_FAILED. Only the owned session was removed and domain 121 was empty afterward.
inferred:
  - No start-state deviation existed at plan request: the trajectory first point is exactly the requested current state for all five arm joints.
  - The rejecting deviation already existed when planning returned. Physics continued for 27 steps during the approximately 0.296-second planning interval, moving joint 2 by +0.6871378028855132 rad and also moving joints 3 and 4 beyond 0.01 rad.
  - No additional sampled drift accumulated after plan response and before the execute call. The failure is therefore not caused by a post-plan application delay or a planner-altered first point.
conclusion: VALID measurement and VALID behavioral failure: uncontrolled robot-state drift while planning makes the exact returned trajectory start stale before ExecuteTrajectory; joint 2 is the first MoveIt-reported rejection under the unchanged 0.01 tolerance.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-040/launch.log (sha256 37ed5ac4e9707a38132112c1ebbe9e72ac0377113a3063f68498df7d360e06e8)
  - /tmp/so101-debug-mujoco-migration/exp-040/measurements.ndjson (sha256 87ae537b26c18391f277d8f06a4381c1695cf6933e7e7f5d5699fb7f6a3fdf8d)
  - /tmp/so101-debug-mujoco-migration/exp-040/delta-analysis.json (sha256 8e3b5691a6ce841dbb759aed8068b2402354e3ca2ef26c3b4219e82f7efc3908)
  - /tmp/so101-debug-mujoco-migration/exp-040/summary.json (sha256 78acfc7676e1f970a08d0891d5b060eea423ce036931a4f2c8d5e54dda73ab94)
  - /tmp/so101-debug-mujoco-migration/exp-040/graph-live.txt (sha256 0e7e4a89606ac7e07b95e31476425f220f78a78e340196841769e53556b568ae)
  - /tmp/so101-debug-mujoco-migration/exp-040/process-tree.txt (sha256 35acc65d125602ea43d8de820d705ca70f8e308edcaf80fd86621db342b57cdb)
  - /tmp/so101-debug-mujoco-migration/exp-040/domain-before.txt and domain-after.txt (each sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-040/provenance.txt (sha256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1)
decision: ACCEPT the root-cause diagnosis and stop. Do not alter production motion behavior, tolerance, threshold, timeout, controller settings, or planning/execution ordering without new user direction.
next_experiment: NONE
```

## Checkpoint CP-057

```yaml
checkpoint_id: CP-057
last_valid_experiment: EXP-040
current_hypothesis: NONE; EXP-040 confirms the exact stale-start mechanism.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; the pre-existing Task 12 dirty implementation remains plus measurement-only structured logging in headless_execution.py, ledger diagnosis, and ignored report. No production behavior fix, reset, stash, clean, stage, commit, or push occurred.
owned_processes: NONE; so101-mujoco-exp040 is absent and domain 121 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - The plan request sample and returned trajectory first point are exactly equal for every arm joint.
  - Over the planning interval, simulation advanced 27 steps/0.272 s and joint 2 drifted +0.6871378028855132 rad. Joints 3 and 4 also exceeded 0.01 rad relative to the trajectory first point.
  - Plan response and immediate pre-execute used the same latest joint sample and atomic tuple; only 0.00012654811143875122 s elapsed and all measured deltas were zero.
  - The root cause is robot physics drift during planning, creating a stale trajectory start before ExecuteTrajectory, not a planner first-point mismatch or post-response delay.
  - EXP-040 is VALID despite the expected behavioral failure because every preregistered measurement, provenance, ownership, graph, exit, cleanup, and hash boundary is complete.
disproven_routes:
  - The trajectory response does not alter or omit the requested start positions.
  - Drift does not accumulate in the diagnostic between plan response and the immediate execute call.
open_risks:
  - Task 12 still lacks successful controller execution, arm convergence, and executed MuJoCo movement proof.
  - Measurement-only observability remains dirty and uncommitted pending user direction on the behavioral correction.
next_command: NONE; report the confirmed root cause and wait for direction before any production behavior fix.
```

## Checkpoint CP-058

```yaml
checkpoint_id: CP-058
last_valid_experiment: EXP-040
current_hypothesis: Controller-state reference/feedback/error/output across the planning interval will distinguish failed physical holding from changing/stale/absent position commands.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; preserved Task 12 dirty implementation plus EXP-040 measurement logging, ledger/report diagnosis; no production behavior correction.
owned_processes: NONE; prior task-owned session is absent and domain 121 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain untouched.
confirmed_conclusions:
  - Installed `/opt/ros/jazzy/share/control_msgs/msg/JointTrajectoryControllerState.msg` defines joint_names and trajectory-point fields reference (desired set point), feedback (latest measured process value), error (reference minus feedback), and output (current controller output), plus speed_scaling_factor.
  - The runtime topic is `/arm_controller/controller_state`; EXP-038/039/040 graph evidence shows it present.
  - Source and installed `ros2_controllers.yaml` match: arm joints 1-5, command_interfaces [position], state_interfaces [position, velocity], open_loop_control false, and no gain or timeout change.
  - EXP-040 logs confirm the active controller lifecycle and state drift but did not subscribe to or preserve the controller's reference/feedback/error/output stream.
disproven_routes:
  - Joint states alone cannot determine whether the position command held constant, changed, or was absent/stale.
open_risks:
  - The diagnostic subscriber must remain read-only and add no controller/action/service call, wait, sleep, ordering, tolerance, gain, timeout, or motion change.
next_command: Run preregistered EXP-041 once after installing finally-flushed read-only controller-state measurement and passing fresh-domain/provenance/ownership checks.
```

## Experiment EXP-041

```yaml
experiment_id: EXP-041
status: VALID
prior_experiment: EXP-040
hypothesis: The complete arm controller-state stream will show whether reference holds the plan-request positions while feedback drifts, reference itself changes, output is absent/stale, or the state message is unavailable.
prediction: A read-only subscription started before plan request records finite complete arm joint_names and available reference/feedback/error/output arrays with header and receipt timestamps across plan request, plan response, and immediate pre-execute. Boundary records correlate joint_states, atomic simulation tuple, and active controller lifecycle without changing the EXP-040 execution outcome or timing semantics.
single_variable: Measurement-only `/arm_controller/controller_state` subscription and finally-flushed serialization; exact EXP-040 behavior, ordering, frozen 0.01 tolerance, timeout, controller gains/config, model, plan, execute call, and motion remain unchanged. No extra wait, spin, sleep, service/action call, command publication, or state mutation is allowed.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and measurement-only subscriber; protected Gazebo tree unchanged.
  - Installed field provenance is `/opt/ros/jazzy/share/control_msgs/msg/JointTrajectoryControllerState.msg`; topic type is `control_msgs/msg/JointTrajectoryControllerState`; source/installed controller config both specify position command and position/velocity state interfaces with open_loop_control false.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; reset-qualified provenance passes with frozen lock.
  - Fresh confirmed-empty ROS_DOMAIN_ID 122, GZ_PARTITION so101_mujoco_task12_exp041, task-owned session so101-mujoco-exp041, evidence root /tmp/so101-debug-mujoco-migration/exp-041/.
  - Existing codex, kimi, and so101-py-qual processes/sessions are preserved and must not be signaled or stopped.
success_criteria:
  - Finally output persists plan_request, plan_response, and pre_execute boundary records containing complete finite six-joint joint_states, atomic tuple, and exact required controller lifecycle states.
  - Finally output persists the complete received arm controller-state stream from before plan request through terminal execution result, including receipt/header times, names, reference, feedback, error, output, and speed scaling exactly as available.
  - Exact joint-2 reference/feedback/error/output evolution identifies one of: fixed desired with drifting actual, changing desired, absent/stale command/output, or unavailable state message.
  - One unchanged safe execute attempt reaches a terminal behavior, direct exit is captured, evidence hashes/process graph are complete, only owned session is cleaned, and domain 122 is empty afterward.
failure_criteria:
  - With all measurement/precondition evidence valid, an unchanged readiness/planning/execution/convergence/MuJoCo/shutdown failure remains a VALID behavioral failure and is terminalized without a production fix.
invalid_criteria:
  - Missing/malformed finally records, incomplete/nonfinite required arrays preventing the preregistered classification, subscriber/instrumentation that changes runtime behavior or adds waits/calls/commands, provenance mismatch, nonempty domain, stale install, ownership defect, incomplete logs/hashes/process evidence, or polluted cleanup makes EXP-041 INVALID.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and measurement-only controller-state subscriber
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  controller_state_definition: /opt/ros/jazzy/share/control_msgs/msg/JointTrajectoryControllerState.msg
  controller_state_topic: /arm_controller/controller_state
  controller_state_type: control_msgs/msg/JointTrajectoryControllerState
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 122
  gz_partition: so101_mujoco_task12_exp041
commands:
  - command: ROS_DOMAIN_ID=122 GZ_PARTITION=so101_mujoco_task12_exp041 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=execute execute:=true simulation_session_id:=task12-exp041 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-041/summary.json
    exit_code: 0
observed:
  - All frozen preconditions passed: domain 122 was empty, exact HEAD/dirty scope and protected Gazebo gates were valid, reset-qualified provenance SHA-256 was b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1, installed/source controller config hashes matched, and only the task-owned session was started.
  - Installed field source `/opt/ros/jazzy/share/control_msgs/msg/JointTrajectoryControllerState.msg` SHA-256 is 7fb2953ccaae67b77ede3a32ef01376763e4aa133064d67d6929ef2fc16582b4. It defines joint_names plus reference, feedback, error, output, and speed_scaling_factor. `ros2 interface show` evidence SHA-256 is 12e53ded1bcf8696bff7e713597bec4341a6f57b51adc8ef1468c18b98b61de7.
  - Source and installed controller config SHA-256 are both 499d471acb93ede255199ac6f220fbff39ae2f01f2277eed8e9967230ebbf16a: position command, position/velocity state, open_loop_control false. The read-only subscriber received eight complete finite five-arm-joint messages from `/arm_controller/controller_state`, proving the topic/message was live even though a later post-shutdown `ros2 topic info` probe found the already-removed topic.
  - Every one of the eight samples contained complete reference, feedback, error, and output position arrays. Every reference array was identical across the stream, every output position array was identical, reference equaled output position in every sample, and speed scaling was 1.0. Message header stamps advanced from simulation time 1.856 to 1.870 s, so the fixed output was current stream data rather than an unavailable message.
  - Joint 2 exact stream values: reference/output remained 0.48821437858892025 rad in all eight samples. Feedback was 0.48777616859526296 first and 0.4873421481950245 last, delta -0.0004340204002384329 rad and range 0.000809004454683182 rad. Error was +0.0004382099936572903 first, ranged 0.000809004454683182, and ended +0.0008722303938957232 rad.
  - Boundary-aligned latest controller samples: at plan request reference/output 0.48821437858892025, feedback 0.48777616859526296, error +0.0004382099936572903; at plan response and pre-execute reference/output remained 0.48821437858892025, feedback was 0.4871243426927168, error +0.001090035896203434. Joint-state joint 2 changed from 0.4891500991800762 at request to 0.4873421481950245 at response, delta -0.001807950985051654 rad.
  - Planning lasted 0.02512173680588603 s and response-to-pre-execute 0.000045596156269311905 s. The unchanged attempt again failed MoveIt start validation, this time reporting joint 3 over 0.01; summary recorded MOVEIT_EXECUTION_FAILED. Finally output preserved all three boundaries and the complete controller stream.
  - Only so101-mujoco-exp041 was removed, domain 122 was empty afterward, and codex, kimi, and so101-py-qual remained untouched.
inferred:
  - Desired/reference does not change during planning. The controller publishes a live, constant position output equal to that reference, so the position command interface is neither absent nor unavailable.
  - Actual feedback changes while desired/output remains fixed; classification is `fixed_reference_and_position_output_with_drifting_feedback`, HIGH confidence for the measured interval.
  - The stale trajectory-start mechanism is downstream of JTC desired generation: physical/simulation feedback can move relative to a current fixed position command. This measurement does not by itself identify MuJoCo actuator/plant tracking internals or explain which joint first exceeds 0.01 on every run; confidence in that deeper mechanism is MEDIUM.
conclusion: VALID measurement and VALID behavioral failure: arm controller desired/reference and position output hold constant while actual feedback drifts; command state is available/current and desired itself is not the source of trajectory-start drift.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-041/controller-state-analysis.json (sha256 5ea2c5b8581c735112f53d9e98a3afd2ad06cbff13e8e3f0fe1dbe24375bb27e)
  - /tmp/so101-debug-mujoco-migration/exp-041/controller-state-stream.json (sha256 9a06fb0ec9d8d318020fd127278674aee2fb7d30086fb96d01a6719f8fedc823)
  - /tmp/so101-debug-mujoco-migration/exp-041/boundary-records.json (sha256 6e4ee843db09d72d29d24b7f9ea3e248086c9c7ddc49d9ed54fe8c5fa186539d)
  - /tmp/so101-debug-mujoco-migration/exp-041/controller-field-config-provenance.txt (sha256 ceb2d4e35b804fc91f0876426ff63e99f6bef24d324f785a627985da35cfb862)
  - /tmp/so101-debug-mujoco-migration/exp-041/controller-state-interface.txt (sha256 12e53ded1bcf8696bff7e713597bec4341a6f57b51adc8ef1468c18b98b61de7)
  - /tmp/so101-debug-mujoco-migration/exp-041/launch.log (sha256 f4274a8859581e7341f79b1e6bb0189faab8dca7d530640da480bff842af20d1)
  - /tmp/so101-debug-mujoco-migration/exp-041/summary.json (sha256 78acfc7676e1f970a08d0891d5b060eea423ce036931a4f2c8d5e54dda73ab94)
  - /tmp/so101-debug-mujoco-migration/exp-041/graph-live.txt (sha256 2407abad0386f4ef3be3251f097539efb4157c840a9599db39bfeeb9e8de1cbb)
  - /tmp/so101-debug-mujoco-migration/exp-041/process-tree.txt (sha256 a196cf4dbc192fb6164212a57487b4d1cd44251d69c80f46cfc2af8c6d82a05a)
  - /tmp/so101-debug-mujoco-migration/exp-041/domain-before.txt and domain-after.txt (each sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-041/provenance.txt (sha256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1)
decision: ACCEPT the controller-side root-cause classification and stop. Do not change production behavior, ordering, tolerance, timeout, gains, controller configuration, actuator parameters, or motion without new user direction.
next_experiment: NONE
```

## Checkpoint CP-059

```yaml
checkpoint_id: CP-059
last_valid_experiment: EXP-041
current_hypothesis: NONE; EXP-041 resolves controller desired/output availability and evolution.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; pre-existing Task 12 dirty implementation plus measurement-only boundary/controller-stream logging, ledger diagnosis, and ignored report. No production behavior fix, reset, stash, clean, stage, commit, or push occurred.
owned_processes: NONE; so101-mujoco-exp041 is absent and domain 122 is empty.
preserved_processes: codex, kimi, and so101-py-qual remain present and untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - Installed field/topic provenance and source/installed position-controller config are exact and hashed.
  - All arm-controller reference/output positions remain fixed and equal across eight current messages; all feedback/error arrays are complete and evolve.
  - Joint 2 reference/output is exactly 0.48821437858892025 rad throughout; feedback/error exact boundary and stream values are recorded in EXP-041.
  - The command interface is present/current, desired does not change, and actual feedback drifts relative to fixed desired/output. Classification confidence is HIGH for the observed controller interval and MEDIUM for deeper MuJoCo plant/actuator causation.
  - EXP-041 is VALID despite the unchanged behavioral failure because field provenance, finally records, lifecycle, graph, exit, cleanup, hashes, and ownership are complete; the post-shutdown topic-info miss is expected and non-causal because eight live messages were preserved.
disproven_routes:
  - Controller state is not unavailable.
  - Desired/reference and output do not change during planning.
  - The position output is not absent; it equals the fixed reference in every sample.
open_risks:
  - The downstream cause of feedback tracking error under a fixed position command is not yet isolated between MuJoCo actuator/plant configuration and hardware-interface command application.
  - Task 12 still lacks successful controller execution, arm convergence, and executed MuJoCo movement proof.
next_command: NONE; report controller-state diagnosis and wait for user direction.
```

## Checkpoint CP-060

```yaml
checkpoint_id: CP-060
last_valid_experiment: EXP-041
current_hypothesis: Freezing MuJoCo before start-state capture and planning, then resuming immediately before ExecuteTrajectory, prevents the confirmed planning-interval drift without changing motion, tolerance, controller, actuator, deadline, or MoveIt adapter behavior.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; preserved Task 12 dirty implementation plus measurement observability and the strict-TDD freeze-plan-resume-execute change. No reset, stash, clean, stage, commit, or push occurred.
owned_processes: NONE; no Task 12 runtime is active before EXP-042 registration.
preserved_processes: codex, kimi, and so101-py-qual remain outside Task 12 ownership and must not be signaled or stopped.
confirmed_conclusions:
  - EXP-040 proved exact request/trajectory equality and drift only during planning; EXP-041 proved current fixed controller reference/output with changing feedback/error.
  - Fix-round-3 RED failed six executable behavior tests because execute mode had no freeze-plan orchestration; RED log SHA-256 is 584c6979aee83557c1a26edab7391c9705797d017dc9c440ed35693d8c1dc92b.
  - Focused GREEN passes 6/6, full headless contract passes 18 with one opt-in skip, Ruff check/format pass, and the two-package symlink build passes.
  - Full direct package pytest passes 192 with three opt-in skips and only the pre-existing ledger-state test failing because it rejects truthful in-progress task status; it must be rerun after final ledger terminalization.
disproven_routes:
  - Planning while physics runs is not safe under the frozen 0.01 start tolerance; EXP-040.
  - Changing desired/output or a missing command interface does not explain the observed planning interval; EXP-041.
open_risks:
  - The freeze-plan-resume execute hypothesis has not yet been tested live.
  - Failure teardown has previously logged a secondary move_group exit -11.
next_command: Confirm ROS_DOMAIN_ID 123 is empty without daemon use, verify exact source/installed/protected-tree provenance and ownership, then transition EXP-042 to RUNNING and execute it once.
```

## Experiment EXP-042

```yaml
experiment_id: EXP-042
status: INVALID
prior_experiment: EXP-041
hypothesis: An authoritative MuJoCo pause before capturing the planning start state, maintained through planning and released immediately before ExecuteTrajectory, prevents the confirmed stale-start rejection while preserving the frozen safe motion and tolerances.
prediction: Pause(true) succeeds and fresh atomic evidence reports paused=true before plan request; publisher_sequence, simulation_step, and joint start positions remain fixed through plan response/pre-execute; pause(false) succeeds and is followed immediately by ExecuteTrajectory; planning and controller execution succeed; all six joints satisfy the existing convergence/hold contract; executed atomic publisher/step movement is positive; only owned processes stop and the fresh domain ends empty.
single_variable: Execute-only ordering changes from plan while running to pause(true), authoritative paused evidence, start capture and plan while paused, then pause(false) immediately followed by ExecuteTrajectory. Dry-run, task12_safe target, 0.01 convergence/start tolerance, controller/actuator parameters, planning limits, overall deadline, MoveIt adapter, overlays, and all other configuration remain unchanged. No StepSimulation call.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and fix round 3; index empty; protected Gazebo tree unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; reset-qualified provenance and installed runtime path pass.
  - Fresh confirmed-empty ROS_DOMAIN_ID 123, GZ_PARTITION so101_mujoco_task12_exp042, task-owned tmux session so101-mujoco-exp042, and evidence root /tmp/so101-debug-mujoco-migration/exp-042/.
  - A task-owned read-only joint-state subscriber records complete six-joint samples and commands nothing; codex, kimi, and so101-py-qual remain preserved.
success_criteria:
  - Exact required graph, TF, Planning Scene, observer/reset services, MoveIt group, action servers, controller mappings, and all three active controller states pass.
  - Pause boundary records prove successful true before plan request and successful false immediately before the ExecuteTrajectory client call; plan-request/response/pre-execute atomic records are authoritative paused=true with no simulation-step advance.
  - Plan is accepted with positive trajectory points; ExecuteTrajectory and the arm controller succeed; arm joints 1-5 converge to task12_safe within unchanged 0.01 rad and independent joint 6 holds within 0.01 rad; maximum arm motion exceeds 0.05 rad.
  - Atomic publisher_sequence and simulation_step advance after resume/execute without reset-epoch change; launch exits zero, evidence/hashes are complete, only owned session/PIDs are cleaned, and domain 123 ends empty.
failure_criteria:
  - With valid source, provenance, fresh-domain, graph, ownership, instrumentation, and cleanup, any pause/order, planning, execution, controller, six-joint convergence, MuJoCo movement, reset-epoch, or shutdown assertion failure is a VALID behavioral failure and terminates Task 12 with no fourth fix.
invalid_criteria:
  - Provenance mismatch, nonempty initial domain, stale install, missing/malformed pause/boundary/joint/atomic evidence, instrumentation pollution, ownership defect, unreliable exit capture, incomplete hashes, or polluted cleanup makes the run INVALID and supports no behavioral conclusion.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and fix round 3
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 123
  gz_partition: so101_mujoco_task12_exp042
commands:
  - command: ROS_DOMAIN_ID=123 GZ_PARTITION=so101_mujoco_task12_exp042 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=execute execute:=true simulation_session_id:=task12-exp042 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-042/summary.json
    exit_code: 1
observed:
  - Host preconditions passed before the task session: domain 123 was empty, the session name was absent, package prefix/provenance/protected-tree isolation passed, exact HEAD/status were captured, and preserved sessions were recorded.
  - The task driver enabled zsh nounset before sourcing ROS. `/opt/ros/jazzy/setup.zsh` and both overlays reported unset trace variables; only `/opt/ros/jazzy` remained searchable and `ros2 launch` exited 1 with package not found.
  - No MuJoCo, controller, MoveIt, workflow, planning, execution, or motion process started. The bounded graph probe was manually ended by killing only session so101-mujoco-exp042; exact task-owned ROS daemon PID 649285 was terminated, and domain 123 ended empty.
inferred:
  - The package lookup failure is entirely harness/source-order pollution and says nothing about the freeze-plan-resume production behavior.
conclusion: INVALID before product behavior. EXP-042 is excluded from the denominator and its ID will not be reused.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-042/launch.log (sha256 f0158dd08219f6a2f1ac06425b6db978ea3a22bfadac3d90a3ef730b3f1f8e9a)
  - /tmp/so101-debug-mujoco-migration/exp-042/launch-exit-code.txt (sha256 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865)
  - /tmp/so101-debug-mujoco-migration/exp-042/domain-before.txt and domain-after.txt (each sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-042/provenance.txt (sha256 76af023c7edb82ce615907266d60c219cf4ed5d2032b44530bd1701eb6759d3b)
decision: REPEAT only after removing harness nounset and using a new experiment ID/domain/session.
next_experiment: EXP-043
```

## Checkpoint CP-061

```yaml
checkpoint_id: CP-061
last_valid_experiment: EXP-041
current_hypothesis: The freeze-plan-resume hypothesis remains untested because EXP-042 never launched the package; corrected instrumentation on a fresh lifecycle can test it.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; exact Task 12 dirty scope remains, with ledger-only EXP-042 terminalization. No production code/config/tolerance/deadline/controller/actuator/motion change followed the invalid run.
owned_processes: NONE; so101-mujoco-exp042 was removed, its exact domain-123 daemon PID was terminated, and domain 123 is empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual were observed and untouched.
confirmed_conclusions:
  - EXP-042 is INVALID before behavior: nounset corrupted ROS setup, the package was unavailable, and no simulator or workflow started.
  - Source/provenance/isolation/domain gates passed independently before the invalid task harness.
disproven_routes:
  - Enabling zsh nounset before ROS setup is not a valid experiment harness; it repeats the known EXP-031-style setup pollution class.
open_risks:
  - The production hypothesis has no live evidence yet.
next_command: Preregister corrected EXP-043 on fresh domain 124 with nounset removed, exact source order, and no-daemon graph polling, then run once.
```

## Experiment EXP-043

```yaml
experiment_id: EXP-043
status: INVALID
prior_experiment: EXP-042
hypothesis: An authoritative MuJoCo pause before capturing the planning start state, maintained through planning and released immediately before ExecuteTrajectory, prevents the confirmed stale-start rejection while preserving the frozen safe motion and tolerances.
prediction: With corrected source-order instrumentation, pause(true) succeeds and fresh atomic evidence reports paused=true before plan request; publisher_sequence, simulation_step, and joint start positions remain fixed through plan response/pre-execute; pause(false) succeeds and is followed immediately by ExecuteTrajectory; planning and controller execution succeed; all six joints satisfy the existing convergence/hold contract; executed atomic publisher/step movement is positive; only owned processes stop and the fresh domain ends empty.
single_variable: Relative to EXP-041 product behavior, execute-only ordering changes to pause(true), authoritative paused evidence, start capture and plan while paused, then pause(false) immediately followed by ExecuteTrajectory. Relative to INVALID EXP-042 instrumentation, zsh nounset is removed and graph polling explicitly disables daemon use. No production variable changed after EXP-042. Dry-run, target, tolerances, controller/actuator parameters, planning limits, deadline, MoveIt adapter, overlays, and all other configuration remain unchanged. No StepSimulation.
lifecycle: FULL_RESTART
preconditions:
  - Exact source HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and fix round 3; index empty; protected Gazebo tree unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install succeeds; reset-qualified provenance and installed package prefix pass.
  - Fresh confirmed-empty ROS_DOMAIN_ID 124, GZ_PARTITION so101_mujoco_task12_exp043, task-owned tmux session so101-mujoco-exp043, and evidence root /tmp/so101-debug-mujoco-migration/exp-043/.
  - Task-owned read-only complete six-joint recorder; all existing sessions/processes preserved.
success_criteria:
  - Required graph/TF/Planning Scene/observer/reset/MoveIt/actions/exact active controllers pass; pause and boundary records prove paused planning with no step advance and successful resume immediately before execute.
  - Positive plan; successful ExecuteTrajectory/controller result; arm joints 1-5 converge to task12_safe and joint 6 independently holds within unchanged 0.01 rad; maximum arm motion exceeds 0.05 rad.
  - Atomic publisher/step movement is positive after resume with unchanged reset epoch; launch/evidence/hashes/ownership/cleanup pass and domain 124 ends empty.
failure_criteria:
  - With valid prerequisites, any behavior-contract failure is VALID and terminates Task 12 with no fourth fix.
invalid_criteria:
  - Any source/provenance/domain/install/instrumentation/ownership/evidence/cleanup pollution is INVALID.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and fix round 3
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 124
  gz_partition: so101_mujoco_task12_exp043
commands:
  - command: ROS_DOMAIN_ID=124 GZ_PARTITION=so101_mujoco_task12_exp043 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=execute execute:=true simulation_session_id:=task12-exp043 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-043/summary.json
    exit_code: 0
observed:
  - Exact source/provenance/isolation/empty-domain/ownership and live graph/controller prerequisites passed. Successful pause(true) completed at monotonic 2694237.58006063; plan-request, response, and pre-execute atomic evidence all remained paused=true at publisher_sequence/simulation_step 138, simulation time 1.48 s, with byte-identical complete six-joint start samples.
  - Pause(false) completed at 2694237.844421942, MoveIt validated the unchanged 0.01 start tolerance, started execution, sent the trajectory to arm_controller, and the controller reported goal reached/success. The headless diagnostic later failed its unchanged independent arm joint convergence timeout.
  - The external recorder received ROS external shutdown, then its finally path called shutdown before writing JSON and raised `rcl_shutdown already called`; no external joint-states.json was persisted. This violates the preregistered mandatory independent six-joint evidence criterion.
  - The owned session ended, graph/process evidence is present, domain 124 ended empty, and unrelated sessions were untouched.
inferred:
  - Freeze-plan-resume removed the stale-start rejection in this run, but the downstream convergence failure cannot be counted without the mandatory external final joint-6 stream.
conclusion: INVALID due evidence-recorder flush pollution. The run supports no product success/failure denominator and its ID will not be reused.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-043/launch.log (sha256 98cdd6b558f1d57c2a1790522bdacfffb512c1cf5c3e4c221c072e7f67100c02)
  - /tmp/so101-debug-mujoco-migration/exp-043/summary.json (sha256 2a3bd242502745cd30233f60c906bed774d2b401aece53c1cd56e164fe18fd5a)
  - /tmp/so101-debug-mujoco-migration/exp-043/pause-boundaries.ndjson (sha256 bf9f72fdd42f753a3b8d2b8e472296f1c1a0bba563a18f542bb5fb10f7a62f4c)
  - /tmp/so101-debug-mujoco-migration/exp-043/boundary-records.ndjson (sha256 6af926006822a5f7cbdf993796dc7f50272b9459bb0c92bf96e352c15003ef13)
  - /tmp/so101-debug-mujoco-migration/exp-043/joint-recorder.log (sha256 5189682eab0d8c747b7437bcd8c461adb49a9fb5c1f33b6da788314bd39af4ce)
  - /tmp/so101-debug-mujoco-migration/exp-043/domain-before.txt and domain-after.txt (each sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
decision: REPEAT only with recorder JSON flushed before conditional rclpy shutdown, under a new ID/domain/session and no production change.
next_experiment: EXP-044
```

## Checkpoint CP-062

```yaml
checkpoint_id: CP-062
last_valid_experiment: EXP-041
current_hypothesis: The post-controller-success joint-convergence timeout seen internally in EXP-043 may be genuine, but only a fresh valid run with independently flushed six-joint evidence can classify it.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; production Task 12 scope unchanged since EXP-043; only ledger and /tmp recorder harness flush ordering changed.
owned_processes: NONE; so101-mujoco-exp043 is absent and domain 124 is empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - EXP-043 validly observed stationary paused planning and a successful controller action, but is INVALID overall because its required external six-joint JSON was not persisted.
  - Recorder root cause is exact: write occurred after unconditional rclpy shutdown, which raised because SIGTERM had already shut the context down. Harness now writes first and calls shutdown only while rclpy remains ok.
open_risks:
  - A valid recurrence of joint convergence timeout is a terminal behavioral failure; no production change or fourth fix is authorized.
next_command: Preregister and run EXP-044 once on fresh domain 125 with the corrected recorder and otherwise identical configuration.
```

## Experiment EXP-044

```yaml
experiment_id: EXP-044
status: VALID
prior_experiment: EXP-043
hypothesis: With valid independent six-joint recording, the exact freeze-plan-resume execute path will either satisfy the full convergence/movement contract or validly reproduce the downstream joint-convergence timeout seen in instrumentation-invalid EXP-043.
prediction: Pause/plan/execute ordering remains stationary and accepted as in EXP-043; recorder flushes complete first/final six-joint samples; controller result, arm convergence, joint-6 hold, atomic movement, and shutdown can then be classified without instrumentation ambiguity.
single_variable: Evidence-harness flush order only relative to INVALID EXP-043: write recorder JSON before conditional rclpy shutdown. Production source/config/order, target, tolerances, controller/actuator parameters, limits, deadline, MoveIt adapter, overlays, and motion are identical. No StepSimulation.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty production paths unchanged; protected Gazebo tree unchanged; index empty.
  - Exact /opt -> dependency -> project source order, reset-qualified provenance, package prefix, fresh confirmed-empty ROS_DOMAIN_ID 125, GZ_PARTITION so101_mujoco_task12_exp044, task-owned session so101-mujoco-exp044, evidence root /tmp/so101-debug-mujoco-migration/exp-044/.
  - Corrected task-owned recorder persists complete six-joint JSON before ROS shutdown; all unrelated sessions/processes preserved.
success_criteria:
  - Full EXP-043 graph/pause/stationary-plan/start-validation/controller gates plus successful diagnostic convergence, independent six-joint target/hold within 0.01 rad, maximum arm motion above 0.05 rad, positive atomic publisher/step movement, unchanged reset epoch, complete hashes/ownership/cleanup, and empty final domain.
failure_criteria:
  - With all prerequisites and external recorder evidence valid, any planning/execution/controller/convergence/joint6/atomic/shutdown behavior failure is VALID, terminal, and permits no further production fix or experiment.
invalid_criteria:
  - Any source/provenance/domain/install/recorder/ownership/evidence/cleanup pollution is INVALID.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and fix round 3
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 125
  gz_partition: so101_mujoco_task12_exp044
commands:
  - command: ROS_DOMAIN_ID=125 GZ_PARTITION=so101_mujoco_task12_exp044 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=execute execute:=true simulation_session_id:=task12-exp044 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-044/summary.json
    exit_code: 0
observed:
  - Exact HEAD/dirty scope, source order, installed package prefix, reset-qualified provenance, protected Gazebo isolation, fresh empty domain 125, session ownership, and live graph prerequisites passed. The headless boundary was reached only after exact required services/actions/TF/controllers were ready; all three required controller states were serialized active.
  - Pause(true) completed successfully at monotonic 2694464.652202733. Plan request, response, and pre-execute records all report paused=true, publisher_sequence 141, simulation_step 141, simulation time 1.532 s, reset epoch 0, and the identical complete six-joint sample. Planning lasted 0.284183059 s with zero atomic/joint change, and the trajectory first point exactly equaled the captured five-arm-joint start.
  - Pause(false) completed successfully at monotonic 2694464.936908546. The MuJoCo log timestamp for resume was 1786370458.851636249; MoveIt rejected `Invalid Trajectory: start point deviates from current robot state more than 0.01 at joint '2'` at 1786370458.852767565, approximately 0.001131316 s later, before controller trajectory handoff.
  - The corrected recorder persisted 128 complete six-joint samples. Joint 6 changed only 0.0018858426702411208 rad from first to last, within the unchanged 0.01 hold gate. Arm feedback moved up to 0.1170006891841896 rad and ended with maximum target error 0.7335231890418306 rad, but this is resume-time physical drift, not successful controller execution.
  - The launch supervisor exited zero after required-process shutdown while the workflow summary recorded MOVEIT_EXECUTION_FAILED. The read-only controller probe was explicitly terminated by exact PID only after its captured live graph became stale during fast failure teardown; internal exact active controller/readiness evidence and action-path logs are complete. The recorder flushed, only owned processes/session/daemon were removed, domain 125 ended empty, and all preserved sessions remained untouched.
inferred:
  - Freeze-plan-resume fixes the planning-interval drift but creates an unavoidable unpaused validation window under this architecture. EXP-043 happened to pass validation, while otherwise identical valid EXP-044 exceeded 0.01 in about 1.13 ms; therefore the hypothesis is not deterministic under the frozen tolerance and current plant/controller behavior.
conclusion: VALID behavioral failure and terminal third-fix result. Planning was stationary and exact while paused, but immediate resume still allowed joint 2 to violate MoveIt's unchanged start tolerance before controller handoff. No fourth production fix, rerun, final success gate, commit, or push is authorized.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-044/launch.log (sha256 26a45ddb94bfdcfb7fc610eb13d7f8b73386017df369bd77046b4c246f587ae9)
  - /tmp/so101-debug-mujoco-migration/exp-044/summary.json (sha256 78acfc7676e1f970a08d0891d5b060eea423ce036931a4f2c8d5e54dda73ab94)
  - /tmp/so101-debug-mujoco-migration/exp-044/joint-states.json (sha256 7a34675cd5ace9cafe7f62f8b28c1043654591c7eaa44363c3e13e36d23a8f10)
  - /tmp/so101-debug-mujoco-migration/exp-044/execution-analysis.json (sha256 db7068780dad049c9baec518b09984b168e7d10e760bea1602b51b806538c2a0)
  - /tmp/so101-debug-mujoco-migration/exp-044/graph-live.txt (sha256 78a35c85af96ffac79cd1be5f9cbc26aeff91a43911aeab20db69fc77f632e7e)
  - /tmp/so101-debug-mujoco-migration/exp-044/process-tree.txt (sha256 36709399ef050ee796a5bb9f9b32679bf7b95dea5fb325bb4b92ecd929ac2f01)
  - /tmp/so101-debug-mujoco-migration/exp-044/domain-before.txt and domain-after.txt (each sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-044/provenance.txt (sha256 76af023c7edb82ce615907266d60c219cf4ed5d2032b44530bd1701eb6759d3b)
decision: ABANDON freeze-plan-resume as insufficient under the frozen architecture; stop Task 12 per the valid-failure/no-fourth-fix rule.
next_experiment: NONE
```

## Checkpoint CP-063

```yaml
checkpoint_id: CP-063
last_valid_experiment: EXP-044
current_hypothesis: NONE; the third and final authorized fix is disproven as a deterministic execution solution.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; exact uncommitted Task 12 independent package/config/launch/headless/test/provenance/metadata paths plus ledger/report. No reset, stash, clean, stage, commit, push, merge, tolerance/deadline/controller/actuator/target/adapter change occurred.
owned_processes: NONE; so101-mujoco-exp044 is absent, exact recorded PIDs are absent, task-owned domain-125 daemon was stopped, and domain 125 is empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain present and untouched.
confirmed_conclusions:
  - Strict TDD proves execute-only pause/authoritative observation/capture/plan/resume/immediate execute ordering, idempotent paused start, planning-failure cleanup, execute-rejection running state, and unchanged dry-run behavior.
  - EXP-044 proves zero physics/joint drift during paused planning and exact trajectory first-point equality, but joint 2 violates 0.01 within about 1.13 ms after resume and before MoveIt controller handoff.
  - The same implementation passed start validation/controller action in instrumentation-invalid EXP-043, so the architecture is nondeterministic rather than uniformly broken at planning.
  - EXP-044 prerequisites, external six-joint recording, failure boundary, provenance, ownership, cleanup, hashes, and protected-tree isolation are valid; it is a behavior failure in the denominator.
disproven_routes:
  - Freeze-plan-resume alone cannot deterministically preserve MoveIt's frozen start-state tolerance through its post-resume validation window.
open_risks:
  - Task 12 still lacks a valid successful controller execution, target convergence, and executed atomic MuJoCo movement proof.
  - Failure teardown still triggers the secondary move_group exit -11.
next_command: NONE; stop without a fourth fix, confirmation experiment, final success gates, stage, commit, or push and report to the orchestrator.
```

## Experiment EXP-045

```yaml
experiment_id: EXP-045
status: VALID
prior_experiment: EXP-044
hypothesis: With the existing fixed arm-controller reference and no planning or execution request, the running MuJoCo plant enters a repeatable stable window within the unchanged 30-second Task 12 total deadline, making settle-and-replan potentially viable without changing tolerance, controller, actuator, target, deadline, or MoveIt behavior.
prediction: A read-only recorder will observe at least 21 consecutive complete finite six-joint samples spanning at least 0.20 simulation seconds, with every adjacent joint sample separated by 0.005 through 0.030 simulation seconds, all six per-joint position ranges at most 0.002 rad, and all six maximum absolute finite-difference velocities at most 0.02 rad/s. Over the same interval, complete arm controller reference/feedback/error/output samples span the joint window; every arm reference is byte-for-value fixed, every arm feedback range is at most 0.002 rad, every maximum absolute arm feedback finite-difference velocity is at most 0.02 rad/s, and every absolute arm controller error is at most 0.002 rad. The recorder reports the first qualifying window entry, qualifying duration, ranges, velocities, errors, controller lifecycle, and atomic evidence without commanding motion.
single_variable: Measurement-only stable-window observation. Relative to EXP-044, no production behavior, planning, execution, pause, threshold, timeout, controller/actuator setting, target, model, source order, or MoveIt adapter is changed; no planning or ExecuteTrajectory goal is sent. The stack runs under the same 30-second overall deadline while an external task-owned recorder continuously observes joint_states, arm controller reference/feedback/error/output, atomic evidence, and controller lifecycle.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus the preserved declared Task 12 dirty scope; index empty; protected Gazebo tree unchanged.
  - Source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> project install; installed package prefix and reset-qualified provenance pass.
  - Fresh confirmed-empty ROS_DOMAIN_ID 126, GZ_PARTITION so101_mujoco_task12_exp045, task-owned tmux session so101-mujoco-exp045, evidence root /tmp/so101-debug-mujoco-migration/exp-045/; only exact recorded owned PIDs/session/domain may be cleaned.
  - Existing codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual processes/sessions are preserved and must not be signaled or stopped.
success_criteria:
  - The preregistered stable predicate qualifies within the unchanged 30-second deadline and is repeatable by construction over 21 consecutive 100 Hz samples spanning at least 0.20 simulation seconds.
  - Evidence includes every raw complete joint/controller/atomic/lifecycle record, exact first-entry monotonic/simulation time, qualifying duration, per-joint ranges/velocities/errors, fixed-reference proof, source/install/process/domain ownership, exits, hashes, and clean owned shutdown with domain 126 empty.
failure_criteria:
  - With valid preconditions and complete instrumentation, absence of a qualifying stable window by the existing deadline is a VALID behavioral failure and terminates the authorized path without production change, tests, further experiment, commit, or push.
invalid_criteria:
  - Any source/install/domain/protected-tree mismatch; a planning, execution, pause, StepSimulation, reset, controller command, or other state-changing instrumentation call; incomplete/nonfinite stream; missing controller/atomic/lifecycle/ownership/exit/hash evidence; or polluted cleanup makes EXP-045 INVALID and supports no behavior conclusion.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths; observation harness only under /tmp
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node plus installed Task 12 robot/controller configuration
  ros_domain_id: 126
  gz_partition: so101_mujoco_task12_exp045
commands:
  - command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh; source /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh; ROS_DOMAIN_ID=126 GZ_PARTITION=so101_mujoco_task12_exp045 ROS2_DISABLE_DAEMON=1 ros2 launch /tmp/so101-debug-mujoco-migration/exp-045/observe_launch.py, with /tmp/so101-debug-mujoco-migration/exp-045/observe_stability.py running concurrently for exactly the preregistered 30-second deadline
    exit_code: 2 for the preregistered observer (no stable window); 143 for exact task-owned launch SIGTERM cleanup after background SIGINT was not handled
observed:
  - Domain 126 was confirmed empty with daemon disabled before launch. Exact HEAD, empty index, declared Task 12 dirty scope, installed config/model hashes, protected Gazebo zero status/diff, task-owned session/PIDs, and the five preserved tmux sessions were captured before the run.
  - The read-only observer ran one continuous data window of 30.00041930982843 monotonic seconds and recorded 2855 complete finite ordered six-joint samples, 14580 complete arm-controller state samples, 2625 atomic MuJoCo evidence samples, 118 controller lifecycle samples, and zero invalid messages. All three required controllers were active in 112 lifecycle samples.
  - No preregistered stable window qualified. `first_stable_window` is null, so there is no stable first-entry time or duration to report. The selected best 21-sample near miss began at monotonic 2698189.375974547 / simulation time 1.034 s and spanned 0.19999999999999996 s through monotonic 2698189.575924635 / simulation time 1.234 s with exact 0.01-second joint intervals and 101 covering controller samples.
  - Best-window six-joint ranges in radians were {1: 0.004581396243925966, 2: 0.04946422629381009, 3: 0.015135787444986115, 4: 0.009863413912184482, 5: 0.00001949159678606564, 6: 0.0010783035515416282}; maximum finite-difference speeds in rad/s were {1: 0.024888018636053055, 2: 0.8614782942395475, 3: 0.26145953546672906, 4: 0.11155060113439687, 5: 0.0001203545562467104, 6: 0.006745104051453747}. Joints 1 through 4 violated at least one 0.002-range/0.02-speed predicate bound.
  - Best-window arm controller feedback ranges in radians were {1: 0.004581396243925966, 2: 0.04947158845380595, 3: 0.015146819879692464, 4: 0.009867947839288294, 5: 0.00001949159678606564}; maximum feedback speeds in rad/s were {1: 0.024894167269590595, 2: 0.9004944339636715, 3: 0.2687972611666032, 4: 0.11210083496431673, 5: 0.00012040637018354152}; maximum absolute errors in radians were {1: 0.0026824341511067335, 2: 0.2683168234475872, 3: 0.07332690094415001, 4: 0.03156323901101571, 5: 0.00003401952157476026}. Controller reference and output each had exactly one unique vector across all 14580 samples, proving the command stayed fixed while feedback failed the gate.
  - Atomic evidence remained session task12-exp045, paused=false, reset_epoch 0 and advanced from sequence/step 0/0 to 2624/2624; no planning, ExecuteTrajectory, pause, reset, StepSimulation, or controller command was issued by instrumentation.
  - Observer exit 2 is the declared behavioral no-window result. Background SIGINT did not terminate ros2 launch, so only its exact recorded PID 765155 received SIGTERM; launch exited 143, exact pane/launch PIDs and session are absent, domain 126 is empty, and the preserved codex/codex-temp/kimi/so101-phy5-v2-r0/so101-py-qual sessions remain unchanged.
inferred:
  - The fixed controller reference is not sufficient for the current plant to settle inside the authorized stability envelope within the existing Task 12 deadline. Because the observation failed its preregistered prerequisite, bounded replan implementation would be speculative and is not authorized.
conclusion: VALID behavioral failure: no repeatable stable window satisfying the frozen predicate occurred within the unchanged deadline. Stop before TDD production work or further live experiments.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-045/stability-observation.json (sha256 880816e35a2e3cfad5aea6db10cad349c211ac194252662a3af61581ea9db78a)
  - /tmp/so101-debug-mujoco-migration/exp-045/observer.log (sha256 dd7bd9736dd2dcc73bd5b45f0df46bee3af1f500f6299f13be0b899266d43a7e)
  - /tmp/so101-debug-mujoco-migration/exp-045/launch.log (sha256 af0faceb095c9300b867be2018b146de06e238404bb7aad7b1ec19391924b9ef)
  - /tmp/so101-debug-mujoco-migration/exp-045/provenance.txt (sha256 7ae9f4cd1714141c4e21a03886945b0728c335b7f646cd56d0aa426bf67ad7e8)
  - /tmp/so101-debug-mujoco-migration/exp-045/reset-qualified-provenance.json (sha256 b16f98a073f3808332ae15761a188c8a60db6ac5dc9439f7bda054c807e4e6d1)
  - /tmp/so101-debug-mujoco-migration/exp-045/observer-exit-code.txt (sha256 53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3)
  - /tmp/so101-debug-mujoco-migration/exp-045/launch-exit-code.txt (sha256 9d9b18720961e9b4689fd763b85e7b6f36160ccd3a8a1c9ddc5103bb0f66c396)
  - /tmp/so101-debug-mujoco-migration/exp-045/git-status-before.txt (sha256 2d8c08a1d5d1853e00eaaa9f8950f688009f90a548439e9580247325db6c65a2)
  - /tmp/so101-debug-mujoco-migration/exp-045/tmux-before.txt (sha256 2769e2a8146442c813f111856567d7a4dcbbcfb706bb6c397767eb1c8e10e842)
decision: STOP. Do not implement settle/replan, modify production behavior, run strict TDD, start another experiment, stage, commit, or push because the authorized observation prerequisite failed validly.
next_experiment: NONE
```

## Checkpoint CP-064

```yaml
checkpoint_id: CP-064
last_valid_experiment: EXP-045
current_hypothesis: NONE; the user-authorized stable-window prerequisite failed under its frozen predicate and existing deadline.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; pre-existing Task 12 independent-package/config/launch/headless/test/provenance/metadata dirty scope plus this ledger is preserved. No production source/config, tolerance, deadline, controller/actuator, target, motion, MoveIt adapter, protected Gazebo, reset, stash, clean, stage, commit, push, or merge change occurred.
owned_processes: NONE; so101-mujoco-exp045 is absent, recorded pane PID 765072 and launch PID 765155 are absent, and domain 126 is empty with daemon disabled.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual sessions remain present and untouched.
confirmed_conclusions:
  - EXP-045 is a VALID observation and behavior failure: the fixed-reference running plant produced complete finite 100 Hz joint/controller/atomic/lifecycle evidence but no 0.20-second window satisfying the preregistered 0.002 rad range/error and 0.02 rad/s speed bounds within the unchanged 30-second deadline.
  - The controller reference/output remained exactly fixed across all 14580 controller samples; moving feedback/error, not a changing command, prevents qualification.
  - The observation issued no planning, execution, pause, reset, StepSimulation, or controller command, and protected/unrelated state was preserved.
disproven_routes:
  - Waiting for an uncommanded fixed-reference stable window within the current Task 12 deadline cannot be assumed as a prerequisite for bounded replanning.
open_risks:
  - Task 12 still lacks successful controller execution, six-joint convergence, and executed MuJoCo movement proof.
  - Launch required exact-PID SIGTERM after background SIGINT was not handled; cleanup nevertheless remained task-owned and domain-clean.
next_command: NONE; stop because the stable-window prerequisite failed validly. Further architecture or controller/plant changes require new user direction.
```

## Experiment EXP-046

```yaml
experiment_id: EXP-046
status: VALID
prior_experiment: EXP-045
hypothesis: Replacing only the unqualified independent MJCF joint/actuator dynamics with the exact shared-lineage SO-101 new-calibration effective values makes the fixed-reference plant satisfy EXP-045's unchanged stability predicate within the same 30-second deadline.
prediction: Under the exact EXP-045 lifecycle and observer, at least 21 consecutive complete finite six-joint samples spanning at least 0.20 simulation seconds qualify: every adjacent joint sample is 0.005 through 0.030 simulation seconds apart; all six joint position ranges are at most 0.002 rad; all six maximum absolute finite-difference speeds are at most 0.02 rad/s; complete arm controller samples span the joint window with byte-for-value fixed reference/output, each feedback range at most 0.002 rad, each feedback speed at most 0.02 rad/s, and each absolute controller error at most 0.002 rad.
single_variable: Relative to EXP-045, only `src/so101_mujoco_demo_py/mjcf/so101.xml` effective dynamics change: joints 1 through 6 damping 0.60, frictionloss 0.052, armature 0.028; position actuators 1 through 6 kp 998.22, kv 2.731, forcelimited true, forcerange [-3.35, 3.35]. Geometry, names, joint ranges, ctrlrange, keyframe, scene gravity/timestep, controller YAML, reference lifecycle, observer/predicate, 30-second deadline, motion target, MoveIt tolerance/adapter, and all other behavior remain identical. No planning, ExecuteTrajectory, pause, reset, StepSimulation, or controller command is issued.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus preserved Task 12 dirty state and the TDD-qualified exact dynamics/provenance/test paths; index empty; Gazebo protected tree diff/status zero.
  - RED old-model regression fails on damping/armature/frictionloss; GREEN exact XML regression, MJCF compile, model parity, provenance, Ruff, isolation, package gates, fresh two-package build/install, and reset-qualified runtime provenance are captured before launch. The known repository-isolation ledger-completion assertion may remain the sole expected package failure because it only accepts Task 1 pending or committed TASK_N_COMPLETE state and cannot truthfully represent this in-progress no-commit Task 12 experiment.
  - Exact source order /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> freshly rebuilt project install.
  - Fresh confirmed-empty ROS_DOMAIN_ID 127, GZ_PARTITION so101_mujoco_task12_exp046, task-owned tmux session so101-mujoco-exp046, evidence root /tmp/so101-debug-mujoco-migration/exp-046/; only exact recorded owned PIDs/session/domain may be cleaned.
  - Existing codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual sessions/processes are preserved and must not be signaled or stopped.
success_criteria:
  - The exact unchanged EXP-045 stable-window predicate qualifies within the same 30-second observation deadline and the first-entry time, duration, joint/controller ranges, velocities, errors, fixed reference/output, lifecycle, and atomic evidence are complete.
  - Raw streams are finite and complete; atomic evidence stays session-bound, unpaused, reset epoch unchanged, and advances; source/install/provenance/ownership/exits/hashes/cleanup are complete and domain 127 ends empty.
failure_criteria:
  - With valid preconditions and complete instrumentation, absence of a qualifying stable window by the existing deadline is a VALID behavioral failure and stops Task 12 without further tuning, execute validation, retry, commit, or push.
invalid_criteria:
  - Source/install/domain/provenance/protected-tree mismatch; predicate/lifecycle drift from EXP-045; planning/execution/pause/reset/StepSimulation/controller command; incomplete/nonfinite stream; ownership/exit/hash/cleanup pollution makes EXP-046 INVALID and supports no dynamics conclusion.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and exact reviewed dynamics paths
  dynamics_source_a: https://github.com/TheRobotStudio/SO-ARM100 commit 7629d2ad9853d10fb903093a33ef6114099d97e5 path Simulation/SO101/so101_new_calib.xml
  dynamics_source_b: https://github.com/johnsutor/so101-nexus commit 3619f7dce086445dc31311edd593a4de93b21c47 path src/so101_nexus/assets/SO101/so101_new_calib.xml; inherited/shared lineage, not independent calibration evidence
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node plus freshly installed Task 12 robot/controller configuration
  ros_domain_id: 127
  gz_partition: so101_mujoco_task12_exp046
commands:
  - command: tmux new-session -d -s so101-mujoco-exp046 'zsh /tmp/so101-debug-mujoco-migration/exp-046/run.zsh'; source order /opt/ros/jazzy/setup.zsh -> /data/work/ws_mujoco_ros2_control_003/install/setup.zsh -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh; ROS_DOMAIN_ID=127 GZ_PARTITION=so101_mujoco_task12_exp046 ROS2_DISABLE_DAEMON=1; exact EXP-045 observation predicate/lifecycle with only installed model dynamics changed
    exit_code: 0 for the observer; task-owned launch terminated by the harness with expected signal exit 143 after observation
observed:
  - Exact source/install MJCF SHA-256 matched at 17e6b5c8670a60de1a78606773fe894f637dd15e6210a8311897a0d48c4a4f83; domain 127 and session name were empty before launch, protected Gazebo status/diff and index were empty, and the exact source order was recorded.
  - The observer ran for 30.016790496185422 wall seconds and captured 2,885 complete finite six-joint samples, 14,615 complete finite arm-controller samples, 2,628 atomic evidence samples, 118 lifecycle samples, and zero invalid messages.
  - The first qualifying window began at simulation time 0.818 s and qualified at 1.018 s: all adjacent joint samples were 0.01 s apart; joint position ranges were at most 6.537781817653188e-12 rad; joint finite-difference speeds were at most 2.174649132644089e-10 rad/s; controller feedback ranges were at most 6.537781817653188e-12 rad; controller feedback speeds were at most 2.54383428384408e-10 rad/s; and maximum controller error was 0.0005400181350476855 rad.
  - Controller reference and output were exactly fixed across the 101 controller samples spanning the first stable window. All three required controllers were active. Atomic evidence stayed unpaused in session task12-exp046 at reset epoch 0 and advanced publisher_sequence/simulation_step from 0/0 to 2627/2627.
  - The task-owned launch PID received only the declared SIGTERM after observation, the task session disappeared, domain 127 ended empty, and all unrelated sessions remained present and untouched.
inferred:
  - The exact reviewed shared-lineage dynamics eliminate the prior fixed-reference drift under the unchanged EXP-045 lifecycle and predicate; this is sufficient to permit exactly one separately preregistered safe-execute validation, but does not itself prove execution.
conclusion: VALID success. The preregistered stable-window gate passed without controller, tolerance, deadline, target, planning, or motion changes.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-046/stability-observation.json (sha256 37e05f107dd185da17c2e00baf86456b7d897555dc189ef19dd4c60dd1f8af52)
  - /tmp/so101-debug-mujoco-migration/exp-046/launch.log (sha256 c7b88a105db6096afa6c8ac67c9663251a68d548e247ff24f6672b3aa336a1ea)
  - /tmp/so101-debug-mujoco-migration/exp-046/observer.log (sha256 11fc74a2af331008c3a84fe9bbb9bcbf01862b4eb9714ba7445b5f2b9a0b53ac)
  - /tmp/so101-debug-mujoco-migration/exp-046/domain-preflight.txt and domain-postflight.txt (each sha256 d207a7d99918d0fd6bf947e0a785fe851692a8c8b25c811cd3aa05c992c514fe)
  - /tmp/so101-debug-mujoco-migration/exp-046/preflight-state.txt (sha256 3ad7f1d489dd4d186afc4de972d6983807dab667b497c87a59532af92511ec05)
decision: PROCEED to the one authorized, separately preregistered safe-execute validation; no tuning or hidden retry.
next_experiment: EXP-047
```

## Checkpoint CP-065

```yaml
checkpoint_id: CP-065
last_valid_experiment: EXP-046
current_hypothesis: The exact reviewed dynamics that validly satisfy the fixed-reference stable-window contract may also preserve the unchanged MoveIt start tolerance through handoff and allow the existing task12_safe trajectory to execute and converge.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; preserved Task 12 dirty scope plus exact dynamics test/MJCF/provenance/ledger changes; protected Gazebo tree unchanged; no reset, stash, clean, stage, commit, or push.
owned_processes: NONE; so101-mujoco-exp046 is absent and ROS domain 127 is empty after exact task-owned launch cleanup.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain present and untouched.
confirmed_conclusions:
  - EXP-046 is a VALID stable-window success under the exact unchanged EXP-045 predicate and deadline.
  - Exact source/install dynamics and provenance, complete finite joint/controller/atomic/lifecycle streams, fixed reference/output, task ownership, cleanup, and protected-tree isolation are proven.
open_risks:
  - Successful MoveIt acceptance, controller execution, independent six-joint convergence, and executed MuJoCo movement remain unproven under the reviewed dynamics.
next_command: Preregister EXP-047 on fresh domain 128 and run exactly one unchanged task12_safe execute validation with independent joint, controller/action, and atomic evidence.
```

## Experiment EXP-047

```yaml
experiment_id: EXP-047
status: VALID
prior_experiment: EXP-046
hypothesis: The exact reviewed dynamics that validly remove fixed-reference drift preserve MoveIt's unchanged 0.01 rad start tolerance through the existing pause-plan-resume handoff and allow the existing task12_safe trajectory to execute and converge.
prediction: The existing execute-only ordering produces an accepted positive MoveIt plan, successful ExecuteTrajectory and arm_controller result, all five arm joints converge to task12_safe within 0.01 rad, joint 6 independently holds within 0.01 rad, maximum arm motion exceeds 0.05 rad, and atomic publisher_sequence/simulation_step advance after resume with unchanged reset epoch.
single_variable: Relative to VALID behavior failure EXP-044, only the exact reviewed MJCF effective dynamics qualified by EXP-046 change. Production ordering, task12_safe target, MoveIt start/convergence tolerance 0.01 rad, overall deadline, planning limits/adapter, controller configuration, URDF/scene, source order, launch arguments, and evidence contract are unchanged. No StepSimulation, reset, grasp, GUI, tolerance change, retry, or tuning.
lifecycle: FULL_RESTART
preconditions:
  - Exact HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and exact reviewed dynamics; index empty; protected Gazebo tree unchanged.
  - Fresh build/install already passed; source/install MJCF hashes and reset-qualified provenance match; exact source order /opt/ros/jazzy -> dependency overlay -> project install.
  - Fresh confirmed-empty ROS_DOMAIN_ID 128, GZ_PARTITION so101_mujoco_task12_exp047, ROS2_DISABLE_DAEMON=1, task-owned tmux session so101-mujoco-exp047, evidence root /tmp/so101-debug-mujoco-migration/exp-047/; only exact owned PIDs/session/domain may be cleaned.
  - The corrected task-owned independent joint recorder persists complete finite six-joint samples before conditional shutdown; live graph/actions/controllers and atomic summary are captured; all unrelated sessions/processes are preserved.
success_criteria:
  - Required MuJoCo/controllers/robot description/TF/MoveIt/planning scene/observer/reset/workflow graph and all three exact active controllers are present.
  - Positive plan; successful MoveIt ExecuteTrajectory and arm_controller FollowJointTrajectory completion; independent arm joints 1-5 converge to task12_safe within unchanged 0.01 rad and joint 6 holds within 0.01 rad; maximum arm motion exceeds 0.05 rad.
  - Atomic publisher_sequence/simulation_step movement is positive after resume with reset epoch unchanged; summary/launch/recorder/graph/controller/action/hashes/ownership/cleanup are complete; task session ends and domain 128 is empty.
failure_criteria:
  - With valid prerequisites and evidence, any planning, action/controller, convergence, joint-6 hold, atomic movement, reset-epoch, shutdown, or required graph assertion failure is a VALID behavioral failure and stops Task 12 without retry, tuning, commit, or push.
invalid_criteria:
  - Any source/install/provenance/domain/protected-tree mismatch, recorder/graph/evidence pollution, missing finite six-joint stream, ownership defect, unreliable exit capture, or polluted cleanup is INVALID and supports no behavior conclusion; no hidden retry is permitted.
provenance:
  source_commit: 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6 plus declared Task 12 dirty paths and exact reviewed dynamics paths
  behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
  dynamics_source_a: https://github.com/TheRobotStudio/SO-ARM100 commit 7629d2ad9853d10fb903093a33ef6114099d97e5 path Simulation/SO101/so101_new_calib.xml
  dynamics_source_b: https://github.com/johnsutor/so101-nexus commit 3619f7dce086445dc31311edd593a4de93b21c47 path src/so101_nexus/assets/SO101/so101_new_calib.xml; shared lineage
  install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/headless_execution
  ros_domain_id: 128
  gz_partition: so101_mujoco_task12_exp047
commands:
  - command: tmux new-session -d -s so101-mujoco-exp047 'export ROS2_DISABLE_DAEMON=1 TASK_EXPERIMENT=047 TASK_DOMAIN=128; zsh /tmp/so101-debug-mujoco-migration/run-exp043.zsh'; launch arguments run_mode:=execute execute:=true simulation_session_id:=task12-exp047 evidence_file:=/tmp/so101-debug-mujoco-migration/exp-047/summary.json
    exit_code: 0
observed:
  - The required MuJoCo, controller, TF, MoveIt, Planning Scene, observer, reset, and workflow graph was present; arm_controller, gripper_controller, and joint_state_broadcaster were active with the exact joint mapping.
  - MoveIt accepted a 19-point plan, validated the unchanged 0.01 rad start tolerance, handed the trajectory to arm_controller, and both ExecuteTrajectory and the controller completed with SUCCEEDED.
  - The headless summary reported arm joints 1 through 5 converged with maximum target error 0.0006389627246847218 rad and maximum arm motion 0.19985624988757617 rad. The separately subscribed recorder persisted 207 complete finite six-joint samples; its final maximum arm target error was 0.0006650965035636253 rad, joint 6 hold error was 3.533242558078027e-07 rad, and maximum arm motion was 0.19987267414821783 rad.
  - Atomic evidence remained in session task12-exp047 at reset epoch 0 and advanced publisher_sequence and simulation_step by 157 after resume. Planning was performed against one authoritative paused boundary at sequence/step 140 before the successful resume and execution.
  - The launch exited 0. The initially still-running task-owned recorder PID 838409 was identified from its recorded PID/cmdline, terminated with SIGTERM only after the run, flushed joint-states.json, and was reaped. The named task session was absent and the final ROS_DOMAIN_ID 128 no-daemon node list was empty; unrelated sessions/processes were not signaled.
inferred:
  - The exact reviewed dynamics are sufficient to remove the fixed-reference drift and preserve MoveIt's unchanged start tolerance through the existing Task 12 pause-plan-resume handoff; no proxy, JTC patch, bounded retry, tolerance change, or hidden rerun was used.
conclusion: VALID success. The single authorized safe execute satisfied planning, action/controller, independent six-joint convergence, atomic MuJoCo movement, reset-epoch stability, ownership, and cleanup contracts.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-047/summary.json (sha256 0da0dd74a2dfa1bdc15500f08d30891fb763803c6da2cdd42d71623ac8ddb65c)
  - /tmp/so101-debug-mujoco-migration/exp-047/launch.log (sha256 faaa01fd892d7dda13449887b292b8c2bd584beb5e414bfc20920af76953c3c1)
  - /tmp/so101-debug-mujoco-migration/exp-047/joint-states.json (sha256 69473b1c82135a0cd21c8b1d25c5a6e918cc19621037a6defb462748c9d3ec46)
  - /tmp/so101-debug-mujoco-migration/exp-047/joint-recorder.log (sha256 2334e5c4cb6d2845430b5b16f035248c6768ec8d730761fe1fa890a498046d37)
  - /tmp/so101-debug-mujoco-migration/exp-047/graph-live.txt (sha256 ba936ae9aaed779f0055c8d552cfa26e62aceb6c9ca16d17d26d45dc8cb32711)
  - /tmp/so101-debug-mujoco-migration/exp-047/controllers-live.txt (sha256 370cf8eecda3dec95a351ed45b3bfcc4d1961242d02a9659c4a9ad9ab6b4ee7a)
  - /tmp/so101-debug-mujoco-migration/exp-047/domain-postflight.txt (empty; sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
decision: KEEP the exact reviewed dynamics and proceed only to Task 12 offline gates/review; no additional live retry.
next_experiment: NONE; this is the single authorized safe-execute validation and no hidden retry is permitted
```

## Checkpoint CP-066

```yaml
checkpoint_id: CP-066
last_valid_experiment: EXP-047
current_hypothesis: NONE; EXP-046 and EXP-047 qualify the exact reviewed dynamics for Task 12 fixed-reference stability and one unchanged safe execute.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; exactly sixteen preserved Task 12/dynamics dirty paths; protected Gazebo tree unchanged; no reset, stash, clean, stage, commit, push, merge, or rebase.
owned_processes: NONE; task-owned recorder PID 838409 was precisely verified, terminated, flushed, and reaped; so101-mujoco-exp047 is absent and ROS domain 128 is empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-046 is VALID success: first stable window 0.818 through 1.018 simulation seconds, maximum joint range 6.537781817653188e-12 rad, maximum speed 2.174649132644089e-10 rad/s, and maximum controller error 0.0005400181350476855 rad under the unchanged predicate.
  - EXP-047 is VALID success: MoveIt/controller SUCCEEDED, independent six-joint evidence converged with maximum arm error 0.0006650965035636253 rad and joint-6 hold error 3.533242558078027e-07 rad, and atomic sequence/step advanced by 157 at unchanged reset epoch 0.
  - The only model change is the explicitly authorized dynamics parameter set; geometry, ranges, ctrlrange, scene, controller YAML, target, tolerance, deadline, and positive-path physics constraints remain unchanged.
open_risks:
  - MoveIt emits a secondary exit -11 during launch-directed teardown after the successful result, but launch ownership cleanup and domain cleanup complete; this does not alter the successful action/controller/joint/atomic behavior and remains a Task 12 teardown risk.
  - Task 12 final offline package gates and scoped review/commit are not part of this handoff and remain pending.
next_command: Run the focused dynamics/model tests, full non-live package suite with isolated ROS/cache paths, Ruff, model parity, dependency provenance, migration isolation, diff check, and protected Gazebo gates; do not rerun EXP-047.
```

## Checkpoint CP-067

```yaml
checkpoint_id: CP-067
last_valid_experiment: EXP-047
current_hypothesis: NONE; the exact authorized dynamics and single safe execute are validly qualified, while Task 12 final commit/review remains outside this handoff.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; exactly sixteen dirty paths comprising the preserved Task 12 scope plus the authorized MJCF, dynamics regression, provenance, and ledger; protected Gazebo status/diff zero.
owned_processes: NONE; the exact task-owned EXP-047 recorder PID 838409 was terminated and reaped after flushing 207 complete finite six-joint samples; ROS_DOMAIN_ID 128 no-daemon node list is empty and so101-mujoco-exp047 is absent.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched; no unrelated process or session was stopped.
confirmed_conclusions:
  - Focused dynamics/MJCF compile/model-parity/provenance tests pass 9/9; Ruff check and format, reset-qualified runtime provenance, migration isolation, git diff check, and protected Gazebo gates pass.
  - Full non-live package pytest initially reported 193 passed, 3 skipped, and one ledger-state contract failure because the Task 1-era test could not represent a later task's truthful terminal next_experiment NONE or generalized pending-commit state. That failure is the RED for the minimal state-machine contract correction performed before Task 12 review.
  - EXP-046 and EXP-047 evidence hashes and exact numerical conclusions are terminalized above; EXP-047 was not rerun.
open_risks:
  - Task 12 still requires full fresh package/colcon verification and scoped review before commit.
  - MoveIt teardown still emits a secondary exit -11 after successful execution; task-owned cleanup and final empty-domain evidence pass.
next_command: NONE; hand off the exact dirty state for Task 12 final review and an explicit decision on the ledger contract before any scoped commit.
```

## Checkpoint CP-068

```yaml
checkpoint_id: CP-068
last_valid_experiment: EXP-047
current_hypothesis: NONE; Task 12 behavior is qualified and only final review, gates, and scoped commit remain.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty; exactly seventeen Task 12 dirty paths after the intentional generalized ledger-contract test correction; protected Gazebo status/diff zero.
owned_processes: NONE after corrective cleanup at 2026-08-11 08:46+08; host preflight found that CP-066/CP-067 had incorrectly declared the EXP-047 session absent while tmux session so101-mujoco-exp047 and its task-owned process tree remained: PID 838316 -> 838410 -> 838945, with PID 838945 blocked in /opt/ros/jazzy/bin/ros2 control list_controllers. Their cmdlines, parentage, PGID 838316, session ownership, and wait states were verified before precisely terminating only that session/tree. All three PIDs and the session are now absent. ROS_DOMAIN_ID 128 `ros2 node list --no-daemon` is empty in domain-128-after-main-cleanup.txt (sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855).
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual were observed running and preserved; no unrelated process or session was stopped.
confirmed_conclusions:
  - CP-066 and CP-067 remain valid for EXP-046/EXP-047 behavior and evidence, but their owned_processes NONE/session-absent cleanup statements were premature and are superseded by this factual cleanup timeline.
  - The Task 1-specific ledger test produced the expected RED against truthful Task 12 terminal state; its minimal generalization accepts EXP-NNN or NONE and applies pending/complete state plus commit-ancestry validation to any numbered Task without fabricating another experiment.
open_risks:
  - MoveIt still emits a secondary exit -11 during launch-directed teardown after the successful execution result; this remains an explicitly uncorrected teardown risk.
  - Final non-live, Ruff, provenance, isolation, diff, protected-tree, and scoped-commit gates remain pending at this checkpoint.
next_command: Complete read-only Task 12 diff review, run all required final gates without rerunning EXP-047, then create the scoped Task 12 commit if every gate passes.
```

## Checkpoint CP-069

```yaml
checkpoint_id: CP-069
last_valid_experiment: EXP-047
current_hypothesis: NONE; Task 12 is review-complete and commit-ready.
working_tree_status: HEAD 4f4bad295ba8ebd11118ed87b432a7eb9b5aa3f6; index empty before restricted staging; exactly seventeen reviewed Task 12 paths; protected Gazebo status/diff zero.
owned_processes: NONE; corrective EXP-047 cleanup from CP-068 remains verified, domain 128 is empty, and no new live process or experiment was started.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - Final non-live pytest passes 194 with three opt-in live skips; Ruff checks all 64 files; two-package colcon reports 447 tests, zero errors, zero failures, and five skips.
  - Reset-qualified runtime provenance passes for upstream 0.0.3 commit 35ba8174b62d9560093614f981a3d4b978a96036 and patch SHA-256 fd2869212d40809dca70f4cc971f93215a64812900cc992817305a33dfcf971e.
  - Migration isolation, git diff check, and both protected Gazebo gates pass. EXP-047 was not rerun.
open_risks:
  - MoveIt emits a secondary exit -11 during launch-directed teardown after the successful action/controller/joint/atomic result; Task 12 does not resolve this teardown-only risk.
next_command: Stage exactly the seventeen reviewed Task 12 paths, rerun cached-diff and protected-tree gates, and commit with the frozen Task 12 subject; do not push.
```

## Experiment EXP-048

```yaml
experiment_id: EXP-048
prior_experiment: EXP-047
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus only the declared Task 13 calibration files and this ledger entry
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: pinned mujoco_ros2_control ros2_control_node plus a task-owned /tmp calibration collector using only ROS 2 controller actions and atomic /so101/simulation/evidence
package_prefixes: mujoco_ros2_control=/data/work/ws_mujoco_ros2_control_003/install; so101_mujoco_support=/data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_support; so101_mujoco_demo_py=/data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py
ros_domain_id: 129
gz_partition: NONE; MuJoCo only
hypothesis: bounded physical controller motions can produce finite atomic distributions for no-contact, left-only, right-only, bilateral-touch, over-compression, micro-lift slip, and stable-hold without importing Gazebo thresholds or using forbidden constraints/state writes
single_variable: regime-specific ROS 2 arm/gripper controller targets while model, dynamics, scene, controller parameters, publish rate, and evidence schema remain fixed
matrix:
  regimes: [no_contact, left_only, right_only, bilateral_touch, over_compression, micro_lift_slip, stable_hold]
  minimum_samples_per_regime: 20
  required_atomic_fields: [simulation_session_id, publisher_sequence, simulation_step, reset_epoch, paused, object_pose_world, object_twist_world, left_fingertip_contacts, right_fingertip_contacts, other_object_contacts, minimum_signed_distance_m, maximum_normal_force_n]
  metrics: [signed_distance_m, normal_force_n, bilateral_presence, object_translation_m, object_linear_speed_m_s, object_angular_speed_rad_s]
success_criteria:
  - all seven regimes have at least twenty finite, strictly ordered, same-session atomic samples with exact model/config/provenance hashes
  - no_contact has neither fingertip contact; left_only and right_only each exhibit exactly their named side; bilateral_touch has both sides; over_compression is physically generated and distinguishable by distance and/or force; micro_lift_slip has controller-caused object motion followed by loss/degradation of hold; stable_hold retains bilateral contact with bounded object twist
  - analyzer emits units, sample counts, quantiles, safety margins, observed false-positive/false-negative matrix, exact hashes, proposed disabled thresholds, and approved_by_user=false
invalid_criteria:
  - missing/cross-session/stale/nonfinite/truncated evidence, inability to produce any required regime without forbidden state manipulation, provenance/readiness/cleanup contamination, or incomplete ownership evidence
failure_criteria:
  - valid evidence shows the seven physical regimes cannot be separated sufficiently to propose fail-closed thresholds; record VALID behavioral failure and stop without inventing values
safety_contract: simulation only; no weld, equality, adhesion, mocap following, teleport, direct object qpos/qvel writes, hardware, Gazebo, GUI, or MoveIt grasp workflow
evidence_root: /tmp/so101-debug-mujoco-migration/exp-048
decision: PENDING
next_experiment: NONE until EXP-048 is terminalized
```

## Checkpoint CP-070

```yaml
checkpoint_id: CP-070
last_valid_experiment: EXP-047
current_hypothesis: EXP-048 will measure the seven required MuJoCo contact regimes under one fixed model/controller stack and support a disabled threshold proposal.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; only this Task 13 ledger preregistration is dirty; protected Gazebo status/diff zero.
owned_processes: NONE; EXP-048 has not started.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain protected.
confirmed_conclusions:
  - Task 12 is committed at 997e8ed95100e4097744c92f1b065613ab390220 with EXP-047 VALID success.
  - EXP-048 is preregistered before tests, runtime, or data collection; no Gazebo/Bullet numerical contact threshold is an input.
open_risks:
  - The exact controller target sequence needed to realize left-only versus right-only and stable-hold versus slip is not yet observed and may validly fail without authorizing model/controller changes.
  - MoveIt teardown -11 remains a Task 12 risk but EXP-048 does not launch MoveIt.
next_command: Add the Task 13 schema/analyzer behavior test only and capture RED caused by the absent calibration artifacts.
```

## Experiment EXP-048 Terminal Result

```yaml
experiment_id: EXP-048
status: INVALID
observed:
  - The task-owned stack reached all three active controllers and published atomic evidence, but the readiness harness invoked unsupported `ros2 topic list --no-daemon` and never entered collect.py.
  - No arm/gripper trajectory, pause, reset, step, MoveIt, or object-state operation occurred; all-atomic-evidence.json was never created.
  - Exact session/PGID and domain-129 daemon were terminated; domain-129 no-daemon postflight is empty.
inferred: NONE about contact regimes; this is a harness instrumentation failure before the experimental variable.
conclusion: INVALID and excluded from all behavioral denominators.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-048/launch.log
  - /tmp/so101-debug-mujoco-migration/exp-048/pane-ownership.txt
  - /tmp/so101-debug-mujoco-migration/exp-048/pstree-start.txt
  - /tmp/so101-debug-mujoco-migration/exp-048/domain-postflight.txt (empty)
decision: Correct only the unsupported topic-readiness invocation and use a fresh experiment/domain.
```

## Experiment EXP-049

```yaml
experiment_id: EXP-049
prior_experiment: EXP-048
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus the unchanged Task 13 calibration files and ledger
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: identical EXP-048 collector; readiness uses ROS2_DISABLE_DAEMON=1 with supported `ros2 topic list`
ros_domain_id: 130
gz_partition: NONE; MuJoCo only
hypothesis: identical to EXP-048
single_variable: measurement harness correction from unsupported `ros2 topic list --no-daemon` to supported `ros2 topic list`; physical controller target matrix is byte-equivalent
success_criteria: identical to EXP-048
invalid_criteria: identical to EXP-048 plus any remaining readiness/ownership/cleanup defect
failure_criteria: identical to EXP-048
safety_contract: identical to EXP-048
evidence_root: /tmp/so101-debug-mujoco-migration/exp-049
decision: PENDING
next_experiment: NONE until terminalized
```

## Checkpoint CP-071

```yaml
checkpoint_id: CP-071
last_valid_experiment: EXP-047
current_hypothesis: EXP-049 can exercise the preregistered contact matrix after correcting only EXP-048's unsupported readiness command.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; Task 13 ledger, config, analyzer, and test only; Gazebo protected tree unchanged.
owned_processes: NONE; so101-mujoco-exp048 and its exact recorded process tree are absent; ROS domain 129 is empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - EXP-048 is measurement INVALID before controller motion and cannot support a contact conclusion.
  - Offline analyzer/schema remains GREEN 6/6 and Ruff passes after formatting.
open_risks:
  - Required physical regimes may still be absent or inseparable; that outcome must stop without model/controller tuning.
next_command: Confirm fresh domain 130, start the corrected task-owned EXP-049 stack, and run the byte-equivalent collector exactly once.
```

## Experiment EXP-049 Terminal Result

```yaml
experiment_id: EXP-049
status: INVALID
observed:
  - The corrected topic command returned, but the shell readiness loop then blocked inside a `ros2 control list_controllers` subprocess after launch logs had already recorded all three controllers active.
  - collect.py never started; there was no controller motion and no atomic matrix evidence.
  - Exact session/PGID and domain-130 daemon were terminated; domain-130 postflight is empty.
inferred: The remaining blind spot is dependence on a separate ros2 CLI readiness process, not controller/product behavior.
conclusion: INVALID and excluded from behavioral denominators.
decision: Remove the external CLI readiness loop; use bounded action-server discovery and atomic callback count inside the collector.
```

## Experiment EXP-050

```yaml
experiment_id: EXP-050
prior_experiment: EXP-049
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus unchanged Task 13 files and ledger
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: EXP-048 physical collector with bounded in-process readiness; no ros2 CLI readiness subprocess
ros_domain_id: 131
gz_partition: NONE; MuJoCo only
hypothesis: identical to EXP-048
single_variable: readiness ownership moves from external ros2 CLI probes to collector-local action-server discovery plus twenty atomic callbacks; physical target sequence is unchanged
success_criteria: identical to EXP-048
invalid_criteria: identical to EXP-048
failure_criteria: identical to EXP-048
safety_contract: identical to EXP-048
evidence_root: /tmp/so101-debug-mujoco-migration/exp-050
decision: PENDING
```

## Checkpoint CP-072

```yaml
checkpoint_id: CP-072
last_valid_experiment: EXP-047
current_hypothesis: collector-local bounded readiness removes the two proven CLI instrumentation blind spots without changing contact physics.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; Task 13 files only; protected Gazebo tree unchanged.
owned_processes: NONE; EXP-049 session/PIDs are absent and domain 130 is empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - EXP-048 and EXP-049 are both INVALID before collector/controller motion and support no contact inference.
open_risks:
  - If EXP-050 cannot establish in-process readiness or a complete regime matrix, stop rather than add another readiness mechanism or tune physics.
next_command: Confirm fresh domain 131 and run EXP-050 once.
```

## Experiment EXP-050 Terminal Result

```yaml
experiment_id: EXP-050
status: INVALID
observed:
  - The collector discovered the evidence publisher but DDS reported incompatible RELIABILITY QoS; zero atomic callbacks arrived during the bounded 30-second readiness window.
  - all-atomic-evidence.json contains zero samples and exact model/config hashes; no arm or gripper trajectory was sent because readiness precedes the first command.
  - The task-owned launch exited through its cleanup trap; exact PGID/session are absent and ROS domain 131 no-daemon postflight is empty.
inferred: The third instrumentation failure is the collector subscription QoS contract, not evidence publication, controller readiness, contact physics, or regime separability.
conclusion: INVALID and excluded from all behavioral denominators. Per CP-072 stop condition, do not add another measurement fix or experiment without explicit direction.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-050/collector.log (sha256 16bc6652b70fc2338082147d4f29f2bc5cd1c943135d2db4e239d5cb3404faa8)
  - /tmp/so101-debug-mujoco-migration/exp-050/all-atomic-evidence.json (sha256 a66db491c70e2e5b3f06cefb0732bdedad76cc59584f04163b327d629acea755)
  - /tmp/so101-debug-mujoco-migration/exp-050/launch.log (sha256 6b13d99ebffc16230042310e0734d5bdcab20ae2ed227cb16427073702c164f1)
  - /tmp/so101-debug-mujoco-migration/exp-050/domain-preflight.txt and domain-postflight.txt (both empty; sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
decision: STOP; no threshold proposal, scoped commit, or Task 14.
```

## Checkpoint CP-073

```yaml
checkpoint_id: CP-073
last_valid_experiment: EXP-047
current_hypothesis: The Task 13 runtime collector must use the evidence publisher's sensor-data/best-effort QoS, but the repeated-instrumentation stop condition forbids implementing or rerunning that correction in this turn.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; four Task 13 dirty paths (ledger, proposed disabled template, analyzer, behavior test); protected Gazebo status/diff zero.
owned_processes: NONE; EXP-048/049/050 sessions and recorded process trees are absent; domains 129, 130, and 131 postflight empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual were observed running and preserved.
confirmed_conclusions:
  - Strict RED was 6 failed because config/analyzer were absent (red.log sha256 3ad59bdbeefc4ec4c2e1c94e5d3e30342cac1653a3411605f6b8c7e53728588d); minimal offline GREEN is 6 passed and Ruff passes 66 files.
  - EXP-048 and EXP-049 are INVALID external-readiness instrumentation failures; EXP-050 is INVALID QoS instrumentation failure. None sent a controller trajectory or produced contact-regime evidence.
  - No contact thresholds are proposed or approved; contact_calibration.yaml remains PLANNED, disabled, and approved_by_user=false.
open_risks:
  - Seven-regime MuJoCo contact distributions and false-positive/negative separation remain wholly unmeasured.
  - The minimum next correction is measurement-only: subscribe with qos_profile_sensor_data, then use a fresh experiment/domain; this requires explicit resume direction after the repeated-failure stop.
  - Task 12 MoveIt teardown -11 remains unchanged.
next_command: NONE; wait for explicit direction on the measurement-only QoS correction. Do not commit, enter Task 14, or fabricate thresholds.
```

## Experiment EXP-051

```yaml
experiment_id: EXP-051
prior_experiment: EXP-050
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus unchanged Task 13 files and ledger
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: EXP-050 collector with only the SimulationEvidence subscription QoS changed to qos_profile_sensor_data
ros_domain_id: 132
gz_partition: NONE; MuJoCo only
hypothesis: matching the evidence publisher's best-effort sensor-data QoS will allow the frozen physical target sequence to produce the seven-regime atomic matrix
single_variable: SimulationEvidence subscriber QoS changes from default reliable depth-100 to qos_profile_sensor_data; readiness, target sequence, model, controllers, and time bounds remain unchanged
success_criteria: identical to EXP-048
invalid_criteria: identical to EXP-048
failure_criteria: identical to EXP-048
safety_contract: identical to EXP-048
evidence_root: /tmp/so101-debug-mujoco-migration/exp-051
decision: PENDING
```

## Checkpoint CP-074

```yaml
checkpoint_id: CP-074
last_valid_experiment: EXP-047
current_hypothesis: EXP-050's observed DDS incompatibility is resolved solely by the standard sensor-data QoS required by the publisher.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; four Task 13 dirty paths; protected Gazebo status/diff zero.
owned_processes: NONE; domains 129 through 131 and all prior calibration sessions are empty/absent.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain protected.
confirmed_conclusions:
  - Goal continuation explicitly resumes progress after CP-073; scope remains the measurement-only QoS correction identified there.
open_risks:
  - QoS compatibility does not imply all physical regimes will occur or be separable.
next_command: Confirm fresh domain 132 and execute EXP-051 exactly once.
```

## Experiment EXP-051 Terminal Result

```yaml
experiment_id: EXP-051
status: INVALID
observed:
  - The wrapper failed before executing the collector because it searched the EXP-050 wrapper, rather than the immutable EXP-048 collector, for the subscription source boundary.
  - No rclpy node, controller command, or atomic callback was created; task-owned launch cleanup completed and domain 132 is empty.
inferred: This is a source-composition error in measurement tooling and carries no runtime/contact evidence.
conclusion: INVALID and excluded from all denominators.
decision: Compose both already-approved readiness and QoS substitutions directly against EXP-048 in one auditable wrapper.
```

## Experiment EXP-052

```yaml
experiment_id: EXP-052
prior_experiment: EXP-051
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus unchanged Task 13 files and ledger
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: immutable EXP-048 physical collector with the EXP-050 bounded readiness and EXP-051 sensor-data QoS substitutions applied directly and asserted exactly once
ros_domain_id: 133
gz_partition: NONE; MuJoCo only
hypothesis: identical to EXP-051
single_variable: no physical variable; measurement wrapper composition is corrected while the intended collector behavior is byte-equivalent to the preregistered EXP-051 target
success_criteria: identical to EXP-048
invalid_criteria: identical to EXP-048
failure_criteria: identical to EXP-048
safety_contract: identical to EXP-048
evidence_root: /tmp/so101-debug-mujoco-migration/exp-052
decision: PENDING
```

## Checkpoint CP-075

```yaml
checkpoint_id: CP-075
last_valid_experiment: EXP-047
current_hypothesis: Direct, asserted composition against the immutable collector removes EXP-051's pre-execution wrapper error.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; Task 13 paths only; protected Gazebo tree unchanged.
owned_processes: NONE; EXP-051 session absent and domain132 empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - EXP-051 is INVALID before ROS/client creation and supports no product inference.
open_risks:
  - EXP-052 may expose the first actual controller/contact boundary; no threshold or physics change is authorized.
next_command: Confirm fresh domain133 and execute EXP-052 exactly once.
```

## Experiment EXP-052 Terminal Result

```yaml
experiment_id: EXP-052
status: INVALID
observed:
  - Wrapper assertion failed before collector execution because literal diff-marker plus signs were accidentally embedded in subscription_old/subscription_new.
  - Read-only comparison proves the immutable collector contains exactly one subscription boundary and one readiness boundary; the generated wrapper, not source/runtime, was defective.
  - No ROS collector node or controller command ran; session absent and domain133 postflight empty.
inferred: NONE about runtime/contact behavior.
conclusion: INVALID and excluded from all denominators.
decision: Build a clean direct wrapper and require offline render assertions before launch.
```

## Experiment EXP-053

```yaml
experiment_id: EXP-053
prior_experiment: EXP-052
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus unchanged Task 13 files and ledger
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: immutable EXP-048 collector with clean, offline-verified direct QoS/readiness substitutions
ros_domain_id: 134
gz_partition: NONE; MuJoCo only
hypothesis: identical to EXP-051
single_variable: correction of literal wrapper text only; intended QoS/readiness and all physical targets are unchanged
success_criteria: identical to EXP-048
invalid_criteria: identical to EXP-048
failure_criteria: identical to EXP-048
safety_contract: identical to EXP-048
evidence_root: /tmp/so101-debug-mujoco-migration/exp-053
decision: PENDING
```

## Checkpoint CP-076

```yaml
checkpoint_id: CP-076
last_valid_experiment: EXP-047
current_hypothesis: Offline verification of the rendered collector prevents another pre-execution wrapper defect.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; four Task 13 paths only; Gazebo protected tree unchanged.
owned_processes: NONE; EXP-052 session absent and domain133 empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - EXP-052 is measurement INVALID before ROS creation; exact immutable boundaries are now known.
open_risks:
  - EXP-053 is still the first opportunity to observe actual controller/contact behavior.
next_command: Offline-render/compile EXP-053 collector, then and only then confirm fresh domain134 and execute once.
```

## Experiment EXP-053 Terminal Result

```yaml
experiment_id: EXP-053
status: VALID
behavioral_result: FAILURE
observed:
  - Offline render gate proved exactly one QoS boundary and one readiness boundary were replaced; rendered collector compiled before launch.
  - Collector completed without stderr and preserved 2126 finite, nontruncated samples from the sole session exp053-contact-calibration with strictly increasing publisher_sequence.
  - Every sample had left_count=0 and right_count=0 across no_contact, descend_preopen, all eight close_scan targets through q6=-0.047608632840292, over_compression q6=-0.059600220867817, stable_hold, and micro_lift_slip.
  - The reported force range 1.1743701417978498 to 1.1907453853021033 N and signed-distance range -0.00018425941641561755 to -0.00017893451818707415 m are from other_object_contacts (cup/table), not fingertip contact.
  - Object world Z remained within 0.07981585620210911 to 0.07982071232213495 m; the commanded arm/gripper sequence neither grasped nor lifted the cup.
  - Session ended normally; domain134 preflight/postflight are empty and the task-owned session/process tree is absent.
inferred:
  - HIGH confidence: the frozen Task 12 joint-space DESCEND endpoint does not place either MuJoCo fingertip collision geom against the cup under the current independent MJCF geometry.
  - No inference is made about usable contact force/distance thresholds because zero fingertip-contact samples exist.
conclusion: VALID behavioral failure. The seven-regime matrix is absent and cannot support a threshold proposal; stop without changing pose, target, model, controller, timeout, or analyzer outputs.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-053/all-atomic-evidence.json (sha256 8546472b1bd6dbe12d34221bc8b920597605090f07cebf4dcd17ba8db8dbed4e)
  - /tmp/so101-debug-mujoco-migration/exp-053/collector.log (empty; sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-053/launch.log (sha256 5ee0be2c9457549ebe66fd4e0b5c723c473e932b7c164c9303a1f32dfad08749)
  - /tmp/so101-debug-mujoco-migration/exp-053/collect.py (sha256 47da25ccc374ae4c7dc171f027aa597f2c6abe594e26a96e49e99857ff48a7e5)
  - /tmp/so101-debug-mujoco-migration/exp-053/rendered.sha256-input.py (sha256 8e11030ec88feb9b09836fc704b8f3298e3bacaf6dc7f8123b796802186aa408)
  - /tmp/so101-debug-mujoco-migration/exp-053/domain-preflight.txt and domain-postflight.txt (both empty)
decision: STOP; no threshold proposal, Task 13 commit, or Task 14.
```

## Checkpoint CP-077

```yaml
checkpoint_id: CP-077
last_valid_experiment: EXP-053
current_hypothesis: The first physical divergence is grasp-pose/collision alignment, upstream of contact-threshold calibration; resolving it requires a separately authorized bounded alignment experiment rather than threshold tuning.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; four Task 13 dirty paths (ledger, PLANNED disabled config, analyzer, test); protected Gazebo diff/status zero.
owned_processes: NONE; so101-mujoco-exp053 and recorded process tree are absent; domain134 no-daemon postflight empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual are observed running and preserved.
confirmed_conclusions:
  - Task 13 offline RED/GREEN is complete, but EXP-053 validly disproves that the frozen target sequence can populate the required contact matrix.
  - Table-contact force/distance must not be reused as a fingertip threshold; no threshold is proposed, enabled, or user-approved.
open_risks:
  - Exact MuJoCo fingertip-to-cup pose alignment is unmeasured; any next work must vary only a bounded arm pose component while retaining physical controller motion and atomic evidence.
  - Task 12 MoveIt teardown -11 remains unchanged.
next_command: NONE; wait for explicit authorization of a bounded grasp-alignment diagnostic. Do not commit Task 13 or enter Task 14.
```

## Experiment EXP-054

```yaml
experiment_id: EXP-054
prior_experiment: EXP-053
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus unchanged Task 13 files and ledger
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: EXP-053 QoS/readiness collector reduced to alignment/no-contact/close-scan/stable-hold only
ros_domain_id: 135
gz_partition: NONE; MuJoCo only
hypothesis: replacing only the misframed frozen arm target with the deterministic in-limit MuJoCo FK candidate will place the cup between the fingertip collision geoms and produce at least twenty consecutive bilateral atomic samples
single_variable: arm alignment target changes from [-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465] to [-1.6427287520696188, 1.74533, -0.71278589545175775, -0.24463292122728339, -2.2078521108750988]; q6 scan/model/controllers/dynamics remain unchanged
offline_prediction:
  frozen_midpoint_m: [-0.00088325, -0.2488925, 0.26697]
  candidate_fixed_geom_m: [0.23368635125741621, 0.017733287074258499, 0.12442274702180217]
  candidate_moving_geom_m: [0.30393243351109345, -0.017917959879469765, 0.089642287283639627]
  candidate_midpoint_target_error_m: 0.0023573710955259622
success_criteria:
  - at least twenty finite, ordered, nontruncated bilateral fingertip samples in one session after a physically commanded q6 close
  - cup remains finite and no forbidden object-state operation occurs
failure_criteria:
  - valid controller/evidence run produces no bilateral contact; stop before another alignment candidate
invalid_criteria:
  - provenance/readiness/QoS/ownership/cleanup failure or incomplete evidence
safety_contract: simulation-only controller motion; no lift, MoveIt, weld, equality, adhesion, mocap, teleport, or direct object qpos/qvel write
evidence_root: /tmp/so101-debug-mujoco-migration/exp-054
decision: PENDING
```

## Checkpoint CP-078

```yaml
checkpoint_id: CP-078
last_valid_experiment: EXP-053
current_hypothesis: A single deterministic arm-target replacement corrects the observed 0.38 m grasp-frame mismatch sufficiently to establish bilateral contact.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; four Task13 paths only; Gazebo protected tree unchanged.
owned_processes: NONE.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - Read-only MuJoCo FK/seeded search evidence is at task13/fk-probe-2.txt and ik-search-precise.txt under the evidence root; no production or model file changed.
open_risks:
  - Midpoint alignment alone may not produce bilateral collision because geom orientation and cup curvature are not optimized.
next_command: Offline-render EXP-054 collector, confirm fresh domain135, and execute exactly once.
```

## Experiment EXP-054 Terminal Result

```yaml
experiment_id: EXP-054
status: VALID
behavioral_result: FAILURE
observed:
  - 1759 finite, nontruncated, strictly ordered samples came from sole session exp054-grasp-alignment.
  - During the single home-to-alignment arm trajectory, 16 left-only samples appeared with maximum reported force 11.595366862398484 N and minimum signed distance -0.0010473808587063134 m; no right/bilateral sample appeared.
  - The physical left-finger sweep displaced the cup from approximately [0.27000035, 0, 0.07982070] m to [0.26886801, 0.05875761, 0.08060937] m, a roughly 58.8 mm Y displacement before q6 close scanning.
  - All later close-scan, over-compression, and stable-hold samples had zero left/right contact because the cup had already been pushed out of the candidate grasp corridor.
  - Domain135 preflight/postflight are empty and task-owned session/processes are absent.
inferred:
  - HIGH confidence: direct single-segment joint interpolation to the collision-aligned endpoint sweeps the fixed fingertip laterally through the cup; the first failing boundary is approach path geometry, not endpoint midpoint or threshold sensitivity.
conclusion: VALID behavioral failure. Per preregistered failure criteria, stop before another alignment candidate; do not tune thresholds or silently add a waypoint.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-054/all-atomic-evidence.json (sha256 58ea2c590313f270e0739af2024ad8ec4a59d038b7ec48aadab7acf3d05dc5e1)
  - /tmp/so101-debug-mujoco-migration/exp-054/launch.log (sha256 c9b4aa7b5a7af7ad7f26e1facd6daf6f0f738eeba3ea64f0906a30e742374b13)
  - /tmp/so101-debug-mujoco-migration/exp-054/collector.log and domain-postflight.txt (both empty; sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
decision: STOP; require explicit approval for an above-object pre-approach waypoint diagnostic.
```

## Checkpoint CP-079

```yaml
checkpoint_id: CP-079
last_valid_experiment: EXP-054
current_hypothesis: A collision-free above-object pre-approach followed by a bounded descent to the same FK endpoint may avoid the observed lateral fixed-finger sweep, but this is a new path variable and is not authorized by EXP-054.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; four Task13 dirty paths; protected Gazebo diff/status zero.
owned_processes: NONE; so101-mujoco-exp054 absent and domain135 empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - Endpoint FK alignment reduced the geometric midpoint error to 2.357 mm, but direct approach caused a large physical cup displacement before closing.
  - No bilateral/stable-hold/micro-lift data exists, so no contact threshold can be proposed or approved.
open_risks:
  - A safe pre-approach waypoint must be derived and validated without model edits, object state writes, or threshold changes.
  - The observed transient force 11.595 N during the failed sweep is a collision hazard signal, not a calibration sample.
next_command: NONE; wait for explicit approval of a single above-object pre-approach waypoint diagnostic. Do not commit Task13 or enter Task14.
```

## Checkpoint CP-080

```yaml
checkpoint_id: CP-080
last_valid_experiment: EXP-054
current_hypothesis: Unchanged from CP-079; an above-object pre-approach may avoid the observed lateral fixed-finger sweep, but no EXP-055 or waypoint execution is authorized.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; exactly four Task 13 dirty paths (ledger, PLANNED disabled calibration config, analyzer, behavior test); protected Gazebo diff/status zero.
owned_processes: NONE; no experiment, ROS stack, build, test, or shutdown diagnostic was started after CP-079.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain untouched.
confirmed_conclusions:
  - User direction freezes sequencing only: first finish and scoped-commit Task 13; then, before Task 14, independently diagnose and fix the Task 12 move_group launch-directed shutdown SIGSEGV/exit -11; only after that may Task 14 begin.
  - The shutdown -11 is a process-lifecycle SIGSEGV risk and must not be described or interpreted as a MoveIt planning error code.
  - The future shutdown task requires its own so101-dev/systematic-debugging ledger experiment, a reproducible RED, single-variable lifecycle/destructor-order A/B, GREEN clean exit 0 without SIGSEGV, exact task-owned/domain cleanup, and non-regression of the existing planning/controller/joint/atomic success evidence.
  - This sequencing direction does not authorize the CP-079 pre-approach waypoint, EXP-055, or any shutdown experiment/fix now.
open_risks:
  - Task 13 remains incomplete because EXP-054 produced only transient left contact and no bilateral calibration matrix; no thresholds can be proposed or committed.
  - move_group launch-directed shutdown still exits -11 after successful Task 12 execution and remains an explicitly deferred lifecycle risk until Task 13 is committed.
next_command: NONE; remain at the Task 13 pre-approach/user-approval boundary. Do not start EXP-055, the shutdown fix, Task 14, or any live stack without new explicit authorization.
```

## Experiment EXP-055

```yaml
experiment_id: EXP-055
prior_experiment: EXP-054
status: PLANNED
lifecycle: FULL_RESTART
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus unchanged Task 13 files and ledger
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: EXP-053 QoS/readiness collector with q6 preopen, one above-object pre-approach, descent to the unchanged EXP-054 FK endpoint, unchanged q6 scan, and no micro-lift command
ros_domain_id: 136
gz_partition: NONE; MuJoCo only
hypothesis: preopening before a collision-free above-object waypoint and then descending to the unchanged FK endpoint avoids EXP-054's lateral fixed-finger sweep and permits at least twenty consecutive bilateral stable-hold samples
single_variable: action path changes from one home-to-endpoint arm segment to q6=0.465038 -> pre-approach [-1.6569865645696216, 1.0199393749999999, -0.41161402045175799, 0.67333582877271692, -2.2953521108750996] -> unchanged endpoint [-1.6427287520696188, 1.74533, -0.71278589545175775, -0.24463292122728339, -2.2078521108750988]
frozen: model, dynamics, controllers, joint limits, q6 scan/limits, endpoint, contact thresholds, cup initial state, deadlines, evidence QoS, and physical no-object-state-write contract
success_criteria:
  - cup displacement before q6 close remains at most 0.003 m and no transient fingertip force exceeds the EXP-054 observed hazard 11.595366862398484 N
  - at least twenty finite, ordered, nontruncated bilateral samples occur during stable_hold in one session
  - object pose/twist remain finite and task-owned/domain cleanup is exact
failure_criteria:
  - valid run has no qualifying bilateral stable hold, exceeds the pre-close displacement bound, or repeats/exceeds the transient collision hazard; stop without another path/target change
invalid_criteria:
  - provenance, readiness, evidence, ownership, or cleanup contamination
safety_contract: simulation only; no MoveIt, lift, weld, equality, adhesion, mocap, teleport, direct qpos/qvel/object state write, hardware, GUI, or Gazebo
evidence_root: /tmp/so101-debug-mujoco-migration/exp-055
decision: PENDING
```

## Checkpoint CP-081

```yaml
checkpoint_id: CP-081
last_valid_experiment: EXP-054
current_hypothesis: The user-authorized pre-approach path prevents the lateral sweep while preserving the same collision-aligned endpoint.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; four Task13 dirty paths; protected Gazebo diff/status zero.
owned_processes: NONE; EXP-055 not started.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain protected.
confirmed_conclusions:
  - User explicitly authorizes EXP-055 as the next bounded simulation-only single-variable experiment and corrects CP-080's pause interpretation.
  - Offline pre-approach midpoint is [0.27010501421268041, -0.000019548144345264348, 0.21988375563066981] m; the 20-point FK path descends to the unchanged endpoint without changing the model.
open_risks:
  - Endpoint fixed-finger geometry may still contact before closing and displace the cup; EXP-055 must fail closed on pre-close displacement/force.
next_command: Offline-render and compile the exact EXP-055 collector; if clean, confirm fresh domain136 and run once.
```

## Experiment EXP-055 Terminal Result

```yaml
experiment_id: EXP-055
status: VALID
behavioral_result: FAILURE
observed:
  - 2362 finite, nontruncated, strictly ordered atomic samples came from sole session exp055-preapproach.
  - q6 preopen and the above-object pre-approach produced zero fingertip contact and negligible cup displacement; this portion behaved as predicted.
  - During descent to the unchanged endpoint, contact transitioned through 43 right-only and 119 left-only samples but never bilateral. Peak reported force was 24.849138808364394 N.
  - The descent displaced the cup from [0.2700003674472347, -9.487605365773128e-09, 0.07982069076083212] m to [0.2664426553797439, 0.014319873698789483, 0.07846153013325524] m, a 0.014817681574346203 m displacement before close scanning, exceeding the frozen 0.003 m gate.
  - Every q6 close-scan, over-compression, and stable-hold sample was left-only; stable_hold contained 197 left-only and zero bilateral samples. Force remained approximately 19.1 to 20.7 N after the failed descent.
  - Domain136 preflight/postflight are empty and the task-owned session/process tree is absent.
inferred:
  - HIGH confidence: the above waypoint prevents the home-path sweep, but joint-space descent changes fingertip orientation/path such that opposite sides contact sequentially and push the cup rather than closing around it.
conclusion: VALID behavioral failure. It exceeds both preregistered safety gates (14.8 mm pre-close displacement versus 3 mm; 24.85 N versus 11.60 N hazard reference) and produces no bilateral stable hold. Stop without changing another waypoint, endpoint, model, controller, q6 scan, or threshold.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-055/all-atomic-evidence.json (sha256 3ba075e7965cfc479730661f35bc163707e6e1cd097a022012844d1cca94e216)
  - /tmp/so101-debug-mujoco-migration/exp-055/launch.log (sha256 850ffb11fb7240a6c74dc11e6be3df8d1686bb3a1b71944c8b1617242c6c5d79)
  - /tmp/so101-debug-mujoco-migration/exp-055/collector.log and domain-postflight.txt (both empty; sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
  - /tmp/so101-debug-mujoco-migration/exp-055/rendered.py (sha256 eb2d988864aef48e363b9e798c2726f428c406f8cf7313b823b0611b92aed9f2)
decision: STOP; Task 13 cannot complete or commit from this matrix, and clean-shutdown/Task14 must not start.
```

## Checkpoint CP-082

```yaml
checkpoint_id: CP-082
last_valid_experiment: EXP-055
current_hypothesis: Joint-space descent does not preserve the desired fingertip world geometry; a future solution would require a separately designed Cartesian/pose-constrained approach or revised endpoint orientation, neither authorized after EXP-055 failure.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; exactly four Task13 dirty paths; protected Gazebo diff/status zero.
owned_processes: NONE; so101-mujoco-exp055 absent and domain136 no-daemon postflight empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, and so101-py-qual remain observed and untouched.
confirmed_conclusions:
  - EXP-055 validates the collision-free pre-approach but validly fails the descent/bilateral contract and its two hard safety gates.
  - Task 13 still has no bilateral, stable-hold, or micro-lift matrix; contact_calibration.yaml remains PLANNED, disabled, and unapproved.
  - CP-080 sequencing remains binding: clean-shutdown -11 work cannot start until Task 13 is complete and committed.
open_risks:
  - A safe pose-constrained descent that preserves fingertip orientation is missing.
  - Peak transient contact 24.849 N demonstrates that another blind joint-space waypoint adjustment is unsafe even in simulation qualification.
next_command: NONE; wait for explicit architecture/direction after the authorized EXP-055 failure. Do not commit Task13, start shutdown work, or enter Task14.
```

## Experiment EXP-056

```yaml
experiment_id: EXP-056
prior_experiment: EXP-055
status: PLANNED
lifecycle: REUSE_STACK
source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus the preserved Task 13 dirty ledger/config/analyzer/test state; no production source or configuration change
install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install
runtime_executable: visualization-only /tmp launch using the same MJCF, controllers, and EXP-055 action targets
ros_domain_id: 137
gz_partition: NONE
headless: false
evidence_plugin_loaded: false
evidence_plugin_exclusion_reason: Visualization-only mitigation for the already observed GUI-mode evidence-plugin mj_contactForce SIGSEGV; this exclusion is not a production configuration change.
hypothesis: The current EXP-055 strategy can be replayed visibly in the MuJoCo GUI so its baseline and final geometry/path outcome can be observed without changing action targets or drawing contact conclusions.
single_variable: Observation mode changes from headless=true to headless=false; the visualization-only /tmp launch omits the evidence plugin solely to avoid the observed GUI-mode mj_contactForce SIGSEGV. MJCF, controllers, and EXP-055 action targets remain identical.
success_criteria:
  - all replay action goals complete without rejection
  - baseline and final MuJoCo GUI states are freshly visible and can be captured as visual evidence
failure_criteria:
  - any action goal is rejected
  - MuJoCo GUI or task-owned stack exits before the required baseline/final observation
invalid_criteria:
  - wrong MJCF/controller/action-target provenance, missing baseline/final visual boundary, ownership contamination, or inability to distinguish fresh frames
evidence_scope:
  - visual evidence only
  - excluded from the Task 13 behavioral denominator
  - cannot support contact presence, contact force, signed distance, calibration threshold, physical grasp, or success claims
safety_contract: simulation only; no hardware, Gazebo, MoveIt grasp, weld, equality, adhesion, mocap following, teleport, or direct object qpos/qvel/state write
evidence_root: /tmp/so101-debug-mujoco-migration/exp-056
decision: PENDING; preregistration only, no stack/action/GUI started
next_experiment: NONE until EXP-056 is explicitly started and terminalized
```

## Experiment EXP-056 Terminal Result

```yaml
experiment_id: EXP-056
status: INVALID
result: ROBOT_NOT_VISIBLE
lifecycle: REUSE_STACK
ros_domain_id: 137
gz_partition: NONE
observed:
  - The existing visualization-only GUI stack was reused; `/tmp/so101_mujoco_visual_replay.py` sent the exact EXP-055 targets and durations one by one.
  - Every action goal was accepted and completed; strategy.exit=0.
  - ros2_control_node PID 1695804 remained alive after the replay completed.
  - User-provided screenshot observation confirms that the robot is not visible at any point in the replay; the white/yellow object near the center of the baseline table cannot be identified as an observable robot.
  - The final frame still visibly contains the cup, while the table and robot are outside the captured view/framing.
  - The GUI remains running in the final state and was not reset.
visual_ambiguity:
  - The final frame alone cannot distinguish an abnormal model pose from a camera auto-framing/viewpoint change.
  - No physical/contact inference is made from the missing table/robot in the final framing.
evidence:
  - /tmp/so101-debug-mujoco-migration/exp-056/baseline.png (sha256 b482fb18fcadbc43791674012eab5a45417167a1aeb985faa3f211044040c25a)
  - /tmp/so101-debug-mujoco-migration/exp-056/final.png (sha256 c67a76e6f13aa1dd1589d216a6f5983c362feb176cb2bc2b1a2c0c3e1796a966)
  - /tmp/so101-debug-mujoco-migration/exp-056/strategy.log (sha256 21584c280c578a3d371021b011e01f10a4e965e5ae84f0b3b1e55928fc3c8929)
decision: INVALID because the preregistered baseline/final visual boundary cannot show robot motion; action completion remains only a control-interface fact.
evidence_scope:
  - remains excluded from the Task 13 behavioral denominator
  - cannot support contact presence, force, signed distance, threshold calibration, physical grasp, or grasp-success conclusions
  - does not supersede EXP-055 VALID behavioral failure
cleanup_state: GUI and ros2_control_node PID 1695804 intentionally remain running at the final state; no reset or cleanup was requested or performed.
next_experiment: NONE
```

## Checkpoint CP-083

```yaml
checkpoint_id: CP-083
last_valid_experiment: EXP-055
current_hypothesis: Unchanged from CP-082 for Task 13 behavior; EXP-056 is invalid because neither baseline nor final visual evidence makes the robot or its motion observable.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index remains empty; the existing four Task 13 dirty paths are preserved; no production source or configuration was changed.
owned_processes: Visualization-only GUI stack remains intentionally running on ROS_DOMAIN_ID 137; ros2_control_node PID 1695804 is alive at the final state and must not be treated as cleaned or abandoned.
preserved_processes: No action, stack, reset, cleanup, or process mutation was performed while terminalizing this ledger entry.
confirmed_conclusions:
  - User-provided screenshot observation confirms the robot never appears; the baseline table's central white/yellow block cannot be classified as an observable robot.
  - EXP-056 is INVALID under its preregistered missing-boundary/inability-to-observe-motion criterion. Every exact EXP-055 action goal being accepted/completed and strategy.exit=0 is retained only as a control-interface fact, not a valid visual replay result.
  - The baseline/final images remain visual artifacts, but they do not establish a robot-motion boundary and final framing is ambiguous between model-pose behavior and camera auto-framing.
  - EXP-056 remains excluded from the Task 13 behavioral denominator and supports no contact, force, signed-distance, threshold, physical-grasp, or grasp-success claim.
open_risks:
  - Task 13 remains blocked at CP-082: no bilateral/stable-hold/micro-lift calibration matrix exists.
  - The visualization-only GUI stack and PID 1695804 remain live by explicit user direction; future ownership/cleanup must preserve this fact.
next_command: NONE; goal remains blocked. Do not reset/stop the GUI, start an experiment, modify production files, or infer Task 13 physical success from EXP-056.
```

## Experiment EXP-057

```yaml
experiment_id: EXP-057
status: PLANNED
prior_experiment: EXP-056 (INVALID)
hypothesis: Rebuilding only the MuJoCo MJCF geometry/rendering and task-object geometry/names from the protected Gazebo reference will make the robot base, complete arm, and open cup visible while preserving the already-qualified kinematics, dynamics, actuators, and controllers.
prediction: Executable structure tests will first fail on the current simplified geometry, then pass after exact visual/collision parity is implemented; the rebuilt MJCF will compile, preserve FK, remain finite/stationary for 10 seconds, and a FULL_RESTART GUI run will freshly show the base, complete arm, open cup, and observable robot motion.
single_variable: Rebuild only MJCF geometry/rendering and task-object geometry/names. Do not change joint transforms, joint limits, dynamics, actuators, or controllers.
lifecycle: FULL_RESTART
authoritative_sources:
  robot_geometry: Protected `src/so101_gazebo_demo_py` URDF expanded with `gazebo_collision_primitives=true`.
  cup_geometry: Protected `src/so101_gazebo_demo_py/worlds/so101_pick_place.sdf` and `src/so101_gazebo_demo_py/config/task_objects/light_plastic_cup.yaml`.
  frozen_local_urdf: `src/so101_mujoco_demo_py/urdf/so101.urdf`; its expanded structural counts and transforms match the authoritative URDF, with only fixed/moving-pad flattened filename prefixes differing.
observed_baseline:
  - The current MJCF has no mesh visual geoms; `robot_collision` uses group 3 and alpha 0.25.
  - The current cup is a solid cylinder with radius 0.035 m, half-height 0.06 m, and mass 0.12 kg.
  - The authoritative cup is an open 13-part compound primitive model with mass 0.020 kg, height 0.090 m, outer radius 0.040 m, wall/bottom thickness 0.002 m, and 12 sides.
preconditions:
  - Use only the frozen authoritative sources above; the protected Gazebo tree remains byte-for-byte unchanged.
  - Preserve the independent `so101_mujoco_demo_py` package and all frozen joint transform, limit, dynamics, actuator, and controller contracts.
  - Establish executable behavior-level RED before changing production MJCF/configuration, then minimal GREEN.
success_criteria:
  - RED-to-GREEN structural tests prove that every key robot body has the visual mesh instance, transform, and material defined by the package-local frozen URDF.
  - Collision structure matches the collision instances, transforms, and asset families from the same URDF; MuJoCo collision geoms may retain independent group/contype settings, while every visual geom has `contype=0` and `conaffinity=0`.
  - Cup visual and collision geometry is the 13-part open compound and matches the authoritative Gazebo SDF dimensions, poses, names, and 0.020 kg mass.
  - MJCF compilation and FK parity pass, followed by a 10-second finite/stationary runtime gate.
  - A FULL_RESTART GUI run produces fresh baseline/final screenshots that visibly contain the robot base, complete arm, and open cup and make robot motion observable.
failure_criteria:
  - Any structural, MJCF compilation, FK parity, 10-second finite/stationary, or visual gate fails under valid provenance and ownership.
invalid_criteria:
  - Wrong authoritative source, stale/old install artifact, process or ROS-domain contamination, or missing/non-fresh baseline or final screenshot.
calibration_invalidation:
  - Task 13 contact calibration on the old geometry cannot migrate to the rebuilt geometry.
  - EXP-055 remains historical evidence for the old model only; after EXP-057 geometry qualification, a new contact-calibration batch is mandatory before proposing thresholds.
provenance:
  source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus the preserved Task 13 dirty state; production remains unchanged at preregistration
  install_overlay: PENDING; must be freshly rebuilt and proven before RUNNING
  runtime_executable: PENDING; FULL_RESTART GUI runtime must resolve only from the qualified MuJoCo overlays
  ros_domain_id: PENDING; select and prove a fresh isolated domain before RUNNING
  gz_partition: NONE
evidence_root: /tmp/so101-debug-mujoco-visual-parity-20260811
safety_contract: Simulation only; no hardware, weld, equality, adhesion, mocap following, teleport, or direct object qpos/qvel/state writes.
commands:
  - command: NONE; preregistration only
    exit_code: PENDING
observed:
  - PLANNED only; no source/configuration/process/runtime action has been taken for EXP-057.
inferred:
  - NONE
conclusion: PENDING
decision: PENDING
next_experiment: NONE until EXP-057 is run and terminalized
```

## Checkpoint CP-084

```yaml
checkpoint_id: CP-084
last_valid_experiment: EXP-055
current_hypothesis: EXP-057 Phase B static GREEN supports the frozen geometry/parity implementation, but EXP-057 remains PLANNED until the separately authorized Phase C finite/stationary and FULL_RESTART visual gates are executed.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; preserved Task 13 ledger/config/analyzer/test plus the unstaged EXP-057 demo/support implementation and tests; protected Gazebo status and d300e7a diff are empty.
owned_processes: NONE. Read-only final `ps -p 1695804` returned no process; this turn did not signal, stop, reset, or otherwise mutate PID 1695804 or any GUI/ROS process.
preserved_processes: No process or tmux session was started or stopped for Phase B.
confirmed_conclusions:
  - The package-local frozen URDF contains 19 visual and 42 collision mesh instances; the GREEN MJCF maps every instance per link/body with exact local transform, asset family, and authoritative material, without aggregate or dummy collision geometry.
  - The `plastic_cup` static contract is an open 13-part visual/collision pair with 12 thin box walls, one bottom cylinder, mass 0.020 kg, authoritative diagonal inertia, package-owned x/y, and bottom resting on the table top.
  - EvidenceBuilder and the plugin accept complete left/right geom sets; executable GTest proves distinct members on both sides classify correctly, while singular parameters remain compatibility-only.
  - Static verification passed: targeted Python 15/15; final geometry/FK suite 11/11; scene compile 1/1; final contracts/provenance/isolation 41/41; demo non-dynamics 203 passed, 3 skipped, 1 deliberately deselected; support GTest 10/10; Ruff, clang-format, isolated two-package build, diff check, isolation, and d300e7a Gazebo gates all exit 0.
  - The kickoff protected-tree diff remains historical: its SHA-256 exactly equals the 8464038-to-d300e7a protected-tree diff (`dfaf6e546353bac864c07f80da9c0366f8a21a636553f97267170524bba8283b`); current protected-tree working status is empty.
disproven_routes:
  - A singleton or added aggregate fingertip evidence geom is not used; it would diverge from the authoritative 42-instance collision structure and omit valid same-side contacts.
open_risks:
  - Phase C has not been qualified and no fresh GUI/FULL_RESTART screenshot exists; robot/cup visibility and observable motion remain unproven.
  - Old-geometry Task 13 contact calibration remains non-transferable; a new calibration batch is mandatory after EXP-057 qualification.
  - The first targeted Python command accidentally selected `test_headless_scene_is_finite_and_stationary_for_ten_seconds`; it passed in accelerated in-process MuJoCo, but was outside the requested Phase B selection and is explicitly excluded from EXP-057/Phase C evidence. No GUI or ROS stack was started.
  - The normal worktree symlink-install retry encountered pre-existing install-tree collisions around the Task 13 `contact_calibration.yaml`; the clean isolated evidence-root build passed and no Task 13 source file was changed or removed.
next_command: NONE; stop at GREEN_STATIC_READY and await explicit Phase C direction. Do not promote EXP-057 from PLANNED or count the accidental in-process dynamics test as runtime qualification.
```

## Experiment EXP-057 Running Transition

```yaml
experiment_id: EXP-057
status: RUNNING
transition_time: 2026-08-11 Asia/Shanghai
prior_experiment: EXP-056 (INVALID)
lifecycle: FULL_RESTART
single_variable: Unchanged from preregistration; only the qualified MJCF geometry/rendering and task-object geometry/names differ from the old model.
provenance:
  source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus the preserved unstaged Task 13 and EXP-057 state
  phase_b_tracked_package_diff_sha256: 8b23b731485fb4f1e9e9747f3a18c6ec5d89f4a7ea70b32949c6dd34060a4ab1
  visual_geometry_test_sha256: acc9b9f178c531788bc63c41d0972f5a5eab5a59387b987b511cefccd317c67e
  install_overlay: /opt/ros/jazzy -> /data/work/ws_mujoco_ros2_control_003/install -> /tmp/so101-debug-mujoco-visual-parity-20260811/install
  installed_scene_sha256: 5ab8a6e2f56c7a7b40adb06f56d4382b90c2d6717c5c192be58537394b292599
  installed_robot_mjcf_sha256: 33f2266fccea1cdf843e6e3510b9a470a0285bf42915c418a11d4a4708204e74
  installed_evidence_plugin_sha256: 6246290cbbb44258fef9aa926e524bd794065175f47171a9d227ae697fef6452
  ros_domain_id: 138
  ros_domain_preflight: `ROS_DOMAIN_ID=138 ros2 node list --no-daemon` returned empty
  gz_partition: NONE
phase_b_evidence:
  - /tmp/so101-debug-mujoco-visual-parity-20260811/build-isolated.log (sha256 979b0e6dec64efcef938132b8a94dbedbd4649f616bb6fcd050c2bc007de4b6c)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/support-gtest-final.log (sha256 351964dbefdb21b925dc1fdcc9bc53daab61cf2a3d8744eb36913150d08add18)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/demo-non-dynamics-tests.log (sha256 b04e3a00214d7304b9b90fede407fbc85e1c9342cf25930bae961b982db72db5)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/mjcf-fk-parity.log (sha256 85b0c3b5a4b851c0888bd9be92989708d69a901a020a981aa5f2fda19dfbe089)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/scene-compile.log (sha256 0234d51de03c8da96792f0ed8d0043697c9f1b2888dbf66e9cf6b5620819903b)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/final-targeted-contracts.log (sha256 40e9ad7d98c2f097664b395d1dd989651c46cda572ae7a1ad91a91826a651440)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/ruff-final.log (sha256 966803eeaadd9efbe57c1f3e92399e3b8c74e032b03b3fccc1fc0aef26c18235)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/isolation-final.log (sha256 da0bc64fdbd48508db4a4037af30987b9fa6b5d750c2acda8c7ebcc4ef8dd0ab)
process_ownership:
  - Existing domain-137 visualization-only stack in tmux `so101-mujoco-gui`, including ros2_control_node PID 1695804, is observed running and preserved; it is not EXP-057-owned.
  - EXP-057 will reuse the tmux session name by adding an isolated domain-138 window/process tree; it will not signal or replace the domain-137 stack.
commands:
  - command: `ROS_DOMAIN_ID=138 ros2 node list --no-daemon`
    exit_code: 0
observed:
  - Phase B source/install hashes are frozen above and the selected fresh domain is empty.
  - Protected Gazebo working status and d300e7a diff remain empty.
inferred:
  - NONE; runtime finite/stationary and visual behavior are not yet claimed.
conclusion: RUNNING; proceed first to the formal 10-second finite/stationary gate.
decision: PENDING
next_experiment: NONE until EXP-057 is terminalized
```

## EXP-057 Running Ownership and Instrumentation Correction

```yaml
correction_time: 2026-08-11 Asia/Shanghai
supersedes:
  - CP-084 `owned_processes: NONE` and its statement that PID 1695804 was absent
  - EXP-057 Running Transition wording that classified the domain-137 GUI stack as external and proposed a parallel domain-138 window
observed:
  - User-provided host evidence and the subsequent read-only process-tree audit confirm that PID 1695804 is alive and belongs to the task-owned EXP-056 visualization-only stack on ROS_DOMAIN_ID 137.
  - tmux `so101-mujoco-gui:0.0` has pane PID 1687386. Its exact task-owned launch tree is rooted at PID/PGID 1695784; tee PID 1695785, robot_state_publisher PID 1695803, and ros2_control_node PID 1695804 belong to that tree.
  - The EXP-056 stack remains running and has not yet been signaled. Other tmux sessions and ROS/Gazebo processes remain preserved.
  - The first formal ten-second gate attempt exited before simulation because the evidence-only ctypes script used `1<<6` for `mjSTATE_CTRL`; the installed MuJoCo header defines `mjSTATE_CTRL = 1<<5`.
correction:
  - The first formal-gate result is INVALID instrumentation evidence and is not an EXP-057 product/model failure.
  - After a corrected formal gate passes, FULL_RESTART must revalidate PID/PGID/cmdline, precisely stop only the task-owned PGID 1695784 tree, prove domain 137 empty, retain and reuse the same tmux pane/window, and start one fresh domain-138 GUI stack. Two GUI stacks must not coexist.
  - No broad `pkill`, unrelated-session mutation, or protected Gazebo mutation is permitted.
evidence:
  - /tmp/so101-debug-mujoco-visual-parity-20260811/formal-10s-gate.json (invalid instrumentation; sha256 43f8d231551dc3fcd4982acce8be453264c3d6be3589e43f9fec1c744835cd3c)
decision: KEEP EXP-057 RUNNING; correct only the measurement bitmask and rerun the formal gate to a new evidence file before any process cleanup.
```

## Checkpoint CP-085

```yaml
checkpoint_id: CP-085
last_valid_experiment: EXP-055
current_hypothesis: EXP-057 geometry remains statically qualified; the first formal runtime attempt was invalid solely because the evidence harness selected the wrong documented MuJoCo state bit.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; all preserved Task 13 and EXP-057 dirty paths remain unstaged; protected Gazebo status and d300e7a diff remain empty.
owned_processes: EXP-056 visualization-only domain-137 stack is task-owned and live in tmux so101-mujoco-gui:0.0; exact launch tree root PID/PGID 1695784 includes tee 1695785, robot_state_publisher 1695803, and ros2_control_node 1695804. It is intentionally retained until the corrected formal gate passes.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and all unrelated ROS/Gazebo processes remain untouched.
confirmed_conclusions:
  - CP-084's PID-absent statement and the EXP-057 Running Transition's external-process classification are false and superseded by the host ownership evidence above.
  - The first formal gate did not simulate; its state-size assertion reflects an instrumentation bitmask error, not geometry or dynamics behavior.
open_risks:
  - Formal ten-second finite/stationary behavior and fresh GUI visibility remain unqualified.
  - Precise EXP-056 teardown must preserve the tmux pane for domain-138 reuse and prove domain 137 empty before launch.
next_command: Run the corrected evidence-only formal ten-second gate against the frozen isolated install and write a new, non-overwriting result file.
```

## Checkpoint CP-086

```yaml
checkpoint_id: CP-086
last_valid_experiment: EXP-055
current_hypothesis: The rebuilt geometry is finite and stationary under the formal ten-second gate; fresh GUI visibility and observable controller-driven motion remain to be reviewed.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; preserved Task 13 and EXP-057 dirty paths remain unstaged; protected Gazebo status and d300e7a diff remain empty.
owned_processes: The exact EXP-056 process group 1695784 was revalidated by PPID/PGID/cmdline and sent SIGINT. Launch 1695784, tee 1695785, robot_state_publisher 1695803, and ros2_control_node 1695804 are absent; tmux pane 1687386 remains alive for the required reuse. Domain 137 no-daemon node list is empty.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and all unrelated ROS/Gazebo processes remain untouched.
confirmed_conclusions:
  - Corrected formal gate exits 0 after 10.000000000000009 simulated seconds; all qpos/qvel/ctrl are finite, table is fixed with zero DOFs, and plastic_cup is present.
  - Cup translation after settle is 2.465955717647727e-08 m; final two-second translation envelope is 2.0779550502379467e-08 m and net speed is 2.8598807963247134e-09 m/s.
  - Corrected evidence SHA-256 is 6af27589572a2f4276fe1a41b0d02e442dffdfc5158d35b332426422558d84c4; domain-137 cleanup evidence is empty SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.
open_risks:
  - Fresh domain-138 GUI provenance, full robot/cup visibility, and visually/numerically observable safe motion are not yet established.
  - The visualization-only launch must omit the evidence plugin only in /tmp and must not support contact conclusions.
next_command: Reuse tmux so101-mujoco-gui:0.0 to launch the frozen isolated overlay on ROS_DOMAIN_ID 138 with headless=false and no evidence plugin, then prove readiness/provenance before capture.
```

## Checkpoint CP-087

```yaml
checkpoint_id: CP-087
last_valid_experiment: EXP-055
current_hypothesis: Fresh domain-138 runtime provenance and controller readiness are valid; only CUA visual framing/inspection remains before any motion is authorized.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; preserved Task 13 and EXP-057 dirty paths remain unstaged; protected Gazebo status and d300e7a diff remain empty.
owned_processes: EXP-057 visualization-only launch PID/PGID 1783524 in retained tmux so101-mujoco-gui:0.0; robot_state_publisher 1783548 and ros2_control_node 1783549 are live on domain 138. The old domain-137 tree remains absent.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and unrelated ROS/Gazebo processes remain untouched.
confirmed_conclusions:
  - Controller readiness is valid: arm_controller, gripper_controller, and joint_state_broadcaster are exactly three active controllers; a complete fresh six-joint sample was received.
  - Runtime provenance resolves demo package to `/tmp/so101-debug-mujoco-visual-parity-20260811/install/so101_mujoco_demo_py`, dependency to `/data/work/ws_mujoco_ros2_control_003/install`, and ros2_control executable to the pinned dependency overlay.
  - Installed scene and robot MJCF hashes remain 5ab8a6e2f56c7a7b40adb06f56d4382b90c2d6717c5c192be58537394b292599 and 33f2266fccea1cdf843e6e3510b9a470a0285bf42915c418a11d4a4708204e74.
  - Two preliminary readiness collectors were INVALID instrumentation: the first produced no durable output; the second parsed controller state from field 2 although `ros2 control list_controllers` places `active` in the final field. The corrected collector uses `$NF`, returns active_count=3, and is the only readiness result used.
  - The local capture helper attempt is INVALID capture instrumentation, not GUI/model failure: it aborted because no visible Ghostty window existed. Per user correction, no capture helper artifact may qualify EXP-057; all subsequent observation and screenshots use ai-station CUA only.
open_risks:
  - CUA has not yet demonstrated that the base, complete arm, and open cup are simultaneously visible in a fresh frame.
  - The visualization-only run omits evidence plugin and therefore supports no contact or threshold conclusion.
next_command: Inventory/create tmux codex-cua, snapshot the live MuJoCo window with CUA, adjust task_camera/free camera only if needed using snapshot/action/fresh-snapshot, and save baseline-cua.png; do not send controller actions.
```

## Checkpoint CP-088

```yaml
checkpoint_id: CP-088
last_valid_experiment: EXP-055
current_hypothesis: The fresh CUA frame exposes a visual-geometry failure rather than a camera-framing absence: the cup and table are clear, but the robot mesh instances appear as separated floating segments rather than one contiguous base-mounted arm.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; all Task 13 and EXP-057 dirty paths remain unstaged; protected Gazebo status and d300e7a diff remain empty.
owned_processes: EXP-057 visualization-only domain-138 launch PID/PGID 1783524, robot_state_publisher 1783548, and ros2_control_node 1783549 remain live in so101-mujoco-gui:0.0. Dedicated CUA-only tmux codex-cua:0.0 is live; it did not edit the repository or ledger.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and unrelated ROS/Gazebo processes remain untouched.
confirmed_conclusions:
  - CUA identified the exact on-screen window `MuJoCo : so101_task_scene` owned by PID 1783549 and saved a fresh 1568x869 window snapshot.
  - The frame visibly contains the open orange cup and table. Multiple yellow/black/blue robot mesh segments and their shadows are visible, but they are spatially separated and floating; no coherent base-to-arm chain can be identified.
  - Because the full scene extents are already inside the frame, camera reframing cannot by itself establish the required contiguous base/complete-arm visual boundary. No CUA input or controller action was sent.
  - Baseline CUA image SHA-256 is 59d33f09c24ab74c39102d191a168f756b88e9b80bce5dd90ca949de97b9d469.
open_risks:
  - EXP-057 remains RUNNING and is not terminalized, but the preregistered visual success criterion is not currently met.
  - The likely visual transform/model cause is not diagnosed in this observation-only checkpoint; no additional source/configuration change is authorized here.
next_command: NONE; keep the domain-138 GUI and CUA baseline available for user inspection. Do not send motion or capture a final frame until the user reviews baseline-cua.png and authorizes the next step.
```

## Checkpoint CP-089

```yaml
checkpoint_id: CP-089
last_valid_experiment: EXP-055
current_hypothesis: CONFIRMED root cause: copying URDF RPY triples into default MuJoCo Euler attributes changes multi-axis rotations; explicit URDF-derived quaternions should restore contiguous robot geometry without changing physics/control contracts.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; preserved Task 13 and EXP-057 dirty paths plus the transform-level test and robot MJCF quaternion correction remain unstaged; protected Gazebo status and d300e7a diff remain empty.
owned_processes: The pre-fix EXP-057 domain-138 visualization stack remains live at launch PID/PGID 1783524 and ros2_control PID 1783549 pending exact restart; codex-cua remains CUA-only.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and unrelated ROS/Gazebo processes remain untouched.
confirmed_conclusions:
  - Transform RED is 1 failed/4 passed: the old model relies on Euler for robot geoms; SHA-256 469a17cbb96b2fc92b4ed59d87d7c77518bff5520aa28a3b39a068150b605501.
  - Direct MuJoCo compilation characterization proves the semantic divergence. For URDF rpy `(1.5708, 1.5708, 0)`, URDF `Rz*Ry*Rx` yields wxyz approximately `(0.5,0.5,0.5,-0.5)` while MuJoCo's old Euler compiles to `(0.5,0.5,0.5,+0.5)`.
  - All 61 robot visual/collision geom Euler attributes were replaced mechanically by explicit normalized URDF-derived wxyz quaternions. Seven body transforms, joints, dynamics, actuators, and cup are unchanged.
  - Targeted transform/MJCF/FK GREEN is 12/12. Isolated two-package rebuild exits 0; host package tests are 219 total, 0 errors/failures, 3 skips (demo 205 passed/3 skipped; support 10/10); Ruff passes 67 files.
  - Formal 10-second gate exits 0 with the same finite/stationary metrics: cup settle translation 2.465955717647727e-08 m and final two-second envelope 2.0779550502379467e-08 m. Evidence SHA-256 is 6af27589572a2f4276fe1a41b0d02e442dffdfc5158d35b332426422558d84c4.
  - The first sandbox package-test attempt is environment-invalid, not a product failure: ROS log writes and DDS sockets were denied, and Ruff identified only formatting in the new test. The corrected host/domain-139 run above is authoritative.
open_risks:
  - Fresh post-fix CUA visual evidence is still required; EXP-057 remains RUNNING and the pre-fix screenshot remains correction evidence.
next_command: Revalidate and SIGINT only PGID 1783524, prove domain 138 empty, reuse so101-mujoco-gui:0.0 with the rebuilt isolated overlay, prove controller readiness, and take a fresh CUA baseline without sending motion.
```

## Checkpoint CP-090

```yaml
checkpoint_id: CP-090
last_valid_experiment: EXP-055
current_hypothesis: Explicit URDF-derived geom quaternions fix a real Euler semantic defect but do not explain the dominant visual separation; the next first-divergence boundary is raw-URDF versus compiled-MuJoCo mesh world AABB/refpose.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; all Task 13/EXP-057 changes remain unstaged; Gazebo protected tree remains zero-diff/status.
owned_processes: Fresh quaternion-fixed domain-138 launch PID/PGID 1820786, robot_state_publisher 1820794, and ros2_control_node 1820795 remain live in so101-mujoco-gui:0.0; codex-cua remains live and CUA-only.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and unrelated ROS/Gazebo processes remain untouched.
confirmed_conclusions:
  - Pre-fix domain-138 PGID 1783524 was precisely stopped after revalidation; domain 138 was empty before the exact pane reuse.
  - Restarted runtime loads installed robot MJCF SHA-256 4f397baae52b45e3983dcbd6e4507c37e3be68b2497436d01101847fbc722f9e and all three controllers are active.
  - The first post-restart CUA call was INVALID instrumentation because session `exp057-baseline` had expired; it was rejected before capture/action. After explicit session revival, CUA saved a fresh frame with SHA-256 ee7c64efd25a4dc81baad1af4a424dbc3bd208f714907af9e7473270a2374614.
  - The post-fix image still shows robot mesh pieces as separated floating segments. No GUI input or controller action was sent. The quaternion change therefore does not by itself satisfy the visual gate.
open_risks:
  - Mesh asset preprocessing/refpose/scale or another transform layer may diverge even though declared geom origins and body joint transforms pass static parity.
  - EXP-057 remains RUNNING and must not be terminalized or advanced to motion.
next_command: Generate read-only per-instance world AABB evidence from raw frozen URDF meshes and from MuJoCo's compiled geom vertex/xpos/xmat data at qpos zero; do not modify production code.
```

## Checkpoint CP-091

```yaml
checkpoint_id: CP-091
last_valid_experiment: EXP-055
current_hypothesis: The remaining visual failure is above the per-instance geometry boundary, likely in the authoritative root/world layout or the visual interpretation of that layout; changing geom transforms further is disproven by exact world-AABB parity and would be a guess.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; preserved Task 13/EXP-057 dirty state plus transform test/quaternion correction remains unstaged; protected Gazebo status and d300e7a diff remain empty.
owned_processes: Quaternion-fixed EXP-057 domain-138 launch PID/PGID 1820786, robot_state_publisher 1820794, and ros2_control_node 1820795 remain live in so101-mujoco-gui:0.0; codex-cua remains live and CUA-only. No motion was sent.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and unrelated ROS/Gazebo processes remain untouched.
confirmed_conclusions:
  - A compiled-model C++ probe uses MuJoCo `geom_xpos`, `geom_xmat`, and compiled mesh vertices at qpos zero; an independent raw-URDF probe transforms every original STL vertex by URDF body and visual-origin transforms.
  - All 19 robot visual instance world AABBs agree between those two paths. Maximum center/extent error is 4.702449263316311e-09 m (`upper_arm_visual_01`); evidence SHA-256 is 04fd68656aa660afe32d501596dab46dcec76aac9e96b1dc6d795dc2bf17bd22.
  - Mesh scale, compiler refpose compensation, geom local orientation, geom local position, and body-chain application therefore reproduce the frozen package-local URDF at the executable world-geometry boundary.
  - The fresh post-fix CUA image still does not satisfy the user-reviewed visual contract and remains visual-gate failure/correction evidence; SHA-256 ee7c64efd25a4dc81baad1af4a424dbc3bd208f714907af9e7473270a2374614.
disproven_routes:
  - Further camera changes cannot repair the observed separation.
  - Further ungrounded geom quaternion/refpose/scale changes are not justified: compiled world AABB already matches raw URDF to nanometer-scale numerical tolerance.
open_risks:
  - The authoritative root/world placement or an upstream frozen-URDF layout assumption may be inconsistent with the intended mounted SO-101 visual scene. This has not been A/B tested and its modification is outside the current no-body/joint-change authorization.
  - EXP-057 remains RUNNING, not terminalized; no action/final capture/contact/calibration claim is permitted.
next_command: NONE; keep the domain-138 GUI available and request direction on a separate root/world-layout diagnostic or authoritative-reference correction. Do not send motion or modify body/joint/dynamics/actuator/cup.
```

## Checkpoint CP-092

```yaml
checkpoint_id: CP-092
last_valid_experiment: EXP-055
current_experiment: EXP-057 RUNNING
current_hypothesis: The Gazebo-aligned pedestal/table/cup world layout is now executable and stable, while the remaining robot appearance is not caused by Convex Hull, BVH, inertia/contact overlays, collision groups, lost faces, smooth normals, or a mesh-to-sphere renderer substitution. The executable q=0 reference pose/view is now the first unresolved boundary; changing joint initial state is not authorized by this round.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; 16 preserved Task 13/EXP-057 dirty paths remain unstaged; protected Gazebo d300e7a diff and worktree status are empty.
owned_processes: Source-matching visualization-only domain-138 stack is restored in retained tmux so101-mujoco-gui:0.0 at launch PID/PGID 1917471 and ros2_control_node PID 1917488. CUA-only session remains separate. No action goal was sent.
preserved_processes: codex, codex-temp, kimi, so101-phy5-v2-r0, so101-py-qual, and all unrelated ROS/Gazebo processes remain untouched. The existing Gazebo reference was captured read-only without focus/input/camera changes.
confirmed_conclusions:
  - CP-091 is corrected: world-AABB parity did not prove viewer rendering. CUA subsequently read Rendering flags (Joint/Inertia/Center of Mass/Contact all off), Group enable (Geom 0/1/2 on and 3/4/5 off), and performed Convex Hull plus BVH A/B. Convex Hull was already off; BVH False became selected; neither changed the robot silhouette.
  - Scene RED was 3 failed/4 passed for absent base_pedestal, wrong table pose/size/pairing, and stale cup/keyframe pose (SHA-256 670d5d4bd0e4030fcbd2c023c94f32a366b19a258ce42ca4f853037879718e90). Minimal GREEN is 7/7 (SHA-256 ee09f6debd9f81709cd5af75a47e8b1c6ed9a94b8e82a9b34c00f597199e9c); combined static/compile gate is 15/15.
  - The scene now includes paired visual/collision base_pedestal at center 0,0,0.17 and full size 0.18,0.18,0.10; paired table at center 0,-0.20,0.10 and full size 0.50,0.60,0.04; plastic_cup and task_start are at 0.02,-0.28,0.165.
  - Formal ten-second gate remains finite with table_dofs=0, cup settle translation 1.854380331613668e-08 m, final two-second envelope 1.3066197182688203e-08 m, evidence SHA-256 ac7504d58ca91e2a34a8b0e6203e55b315a4edae76ae74f3e619b0f85505551c.
  - Gazebo read-only CUA reference shows the same asset family as detailed mechanical parts (SHA-256 9fce3adeaedb715accfdf80c244b1ccad1367588c17024d8c7e26c20378fe930). MuJoCo preserves every raw STL face exactly and all 19 robot visuals enter mjvScene as mjGEOM_MESH, not sphere (probe SHAs 0b38c1ec8c188aabda0581960f36f16271324f81beca5f9afe427456155528d6 and 846919f723d5e399ba647600fec9526238478fa3d6f7418ccf92cb6c68f6f44e).
  - Asset-level smoothnormal=false was tested as a single-variable A/B after a strict RED; static/10-second gates passed but the fresh CUA silhouette did not change. The test and production attributes were removed, rebuilt, and the source-matching runtime restored.
  - One HiDPI-misdirected CUA panel operation triggered the known GUI display-thread SIGSEGV in update_sim_display; its launch shut down automatically. Exact task-owned leftovers were cleaned and a fresh source-matching stack was restored. This is GUI instrumentation/runtime risk, not physics qualification evidence.
open_risks:
  - EXP-057 remains RUNNING. The user-reviewed full-arm visual criterion is not yet met, so no motion/final frame/contact/calibration conclusion is allowed.
  - The source-matching q=0 reference pose/view differs materially from the preserved Gazebo reference pose. Any change to robot keyframe/controller initial state needs an explicit frozen pose contract; no joint transform, limit, dynamics, actuator, controller, or target was changed here.
next_command: Review and authorize an exact robot reference-pose contract (or a single-mesh visual qualification fixture) before changing robot qpos; do not send action goals or terminalize EXP-057.
```

## Correction to CP-092 and Experiment EXP-058

```yaml
correction_to: CP-092
reason: The prior render-scene probe interpreted MuJoCo geom enum value 2 as mesh. In MuJoCo, value 2 is mjGEOM_SPHERE and value 7 is mjGEOM_MESH. The executable probe therefore proves the opposite of CP-092's renderer-substitution claim: every robot geom with model_type=2/rendered_type=2 is a sphere even though dataid references a loaded mesh asset.
superseded_claim: All 19 robot visuals enter mjvScene as mjGEOM_MESH, not sphere.
preserved_evidence: /tmp/so101-debug-mujoco-visual-parity-20260811/render-scene-probe.txt

experiment_id: EXP-058
prior_experiment: EXP-057 RUNNING
status: PLANNED
lifecycle: FULL_RESTART
hypothesis: The robot geoms compile as spheres because their robot_visual and robot_collision defaults omit type="mesh"; explicitly inheriting type="mesh" will make the existing ai-station worktree assets render and collide as the paired detailed meshes without changing transforms, qpos, dynamics, actuators, controllers, or mesh locations.
prediction:
  - A source contract test will fail because both robot geom defaults omit type="mesh".
  - After the one-variable patch, the source contract and MJCF compile gates will pass, a compiled-model probe will report mjGEOM_MESH (enum 7) for all robot visual/collision geoms, and a fresh CUA frame will show detailed mechanical links instead of spheres.
single_variable: Add type="mesh" to the robot_visual and robot_collision default geoms in src/so101_mujoco_demo_py/mjcf/so101.xml.
authoritative_reference: https://github.com/johnsutor/so101-nexus/blob/main/src/so101_nexus/assets/SO101/so101_new_calib.xml explicitly types mesh geoms; retain this package's existing assets/... file attributes because the ai-station worktree stores meshes under src/so101_mujoco_demo_py/mjcf/assets.
success_criteria:
  - RED fails only on the missing explicit mesh type, then GREEN passes.
  - All robot visual and collision geoms compile as mjGEOM_MESH enum 7 and retain valid mesh data ids.
  - Visual/collision instance parity and asset existence tests pass with no Gazebo changes.
  - A ten-second finite/stationary gate passes after the collision type correction.
  - Exact task-owned FULL_RESTART provenance is valid and a fresh ai-station CUA image visibly shows detailed mechanical robot geometry.
failure_criteria:
  - Any geom remains sphere/primitive, MJCF fails to compile, stability regresses, or fresh CUA still shows spherical robot geometry.
invalid_criteria:
  - Stale install, wrong overlay/domain, non-CUA screenshot, process contamination, or changes outside the single-variable production patch.
provenance:
  source_commit: 997e8ed95100e4097744c92f1b065613ab390220 plus preserved unstaged Task 13/EXP-057 work
  install_overlay: /tmp/so101-debug-mujoco-visual-parity-20260811/install after fresh rebuild
  runtime_executable: pinned mujoco_ros2_control overlay plus freshly rebuilt so101_mujoco_demo_py
  ros_domain_id: 138 after exact task-owned restart
  gz_partition: NONE
evidence_root: /tmp/so101-debug-mujoco-visual-parity-20260811
safety_contract: Visualization and static/runtime stability only; no action goals, robot motion command, hardware, teleport, direct state writes, equality, weld, adhesion, or mocap following.
decision: PENDING; preregistration and RED-test addition only.
```

## Experiment EXP-058 Terminal Result

```yaml
experiment_id: EXP-058
status: VALID
result: ROBOT_MESH_VISUAL_RESTORED
lifecycle: FULL_RESTART
single_variable_applied: Added type="mesh" only to the robot_visual and robot_collision default geoms; retained every existing assets/... file attribute and did not modify mesh assets, transforms, qpos, dynamics, actuators, controllers, scene layout, or Gazebo.
root_cause:
  - MJCF geom defaults to sphere when type is omitted.
  - A mesh attribute/data id alone does not make the geom a mesh; the corrected MuJoCo enum interpretation is mjGEOM_SPHERE=2 and mjGEOM_MESH=7.
red:
  result: 1 failed on visual_default type None versus mesh
  evidence: /tmp/so101-debug-mujoco-visual-parity-20260811/robot-geom-type-red.log
  sha256: 7da232842880bcdaac78a45f5b8df8be196112d48fc27b173906f5cec7ba02c7
green:
  targeted_source_compile: 11 passed
  compiled_geometry: 19 robot visual plus 42 robot collision geoms; all type=7, dataid>=0, bad=0
  package_tests: 207 passed, 3 skipped
  ruff: All checks passed; 67 files already formatted
  isolated_build: 2 packages finished
runtime_gate:
  simulation_seconds: 10.000000000000009
  finite_state: true
  table_dofs: 0
  cup_translation_after_settle_m: 1.8543803469486458e-08
  final_two_second_translation_envelope_m: 1.3066197291198687e-08
runtime_provenance:
  launch_pid_pgid: 1984990
  ros2_control_node_pid: 1984999
  ros_domain_id: 138
  package_prefix: /tmp/so101-debug-mujoco-visual-parity-20260811/install/so101_mujoco_demo_py
  ros2_control_executable: /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node
  installed_robot_mjcf_sha256: cf888f91218deaef6b5d394ab6ace0cd3a9cc9b5b2e9a2fdc5ce1423503253bd
  controllers: arm_controller, gripper_controller, and joint_state_broadcaster active
cua_observation:
  - Fresh CUA window snapshot from MuJoCo PID 1984999/window 81788935 visibly contains the mounted robot base, detailed servo housings, mechanical links, wrist, gripper/fingertips, pedestal, table, and open compound cup.
  - The prior yellow/black/blue spherical blobs are absent. No GUI input, camera change, controller action, or motion goal was sent.
  evidence: /tmp/so101-debug-mujoco-visual-parity-20260811/exp058-cua-fresh.png
  sha256: d88b1669b031d767c3d9d71e40392dc88da90de5b5e8e969dcca2a9b4fbf60a2
evidence:
  - /tmp/so101-debug-mujoco-visual-parity-20260811/robot-geom-type-green-source.log (sha256 1d6b6c9aebd712df39deb27f2f3a2e22e9c38806c7802572491d6f47d6e81d88)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/robot-geom-probe-green.txt (sha256 9b5a5fe82e7f572125471f723102fe9e876c7b1420f5346f60b5fc27bbe9f7d7)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/robot-mesh-fix-10s.json (sha256 04acbf99ab5f1949315d3bcf50fc0ee4f679254d3d7a003537cac8ea0d98fd8c)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/robot-mesh-fix-rebuild.log (sha256 8e9f615507e054f6bc4185e213363bff84dd8f4a44d63f9f69ceb5876dd16187)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/exp058-demo-pytest.log (sha256 6bde2d889c1a6e99829c31e59b44bb608e5122ec91061f4390e793d7a14deb15)
  - /tmp/so101-debug-mujoco-visual-parity-20260811/exp058-ruff-valid.log (sha256 966803eeaadd9efbe57c1f3e92399e3b8c74e032b03b3fccc1fc0aef26c18235)
invalid_instrumentation:
  - The first combined GREEN command lacked source PYTHONPATH and failed test collection; the corrected source-qualified command is authoritative.
  - The first corrected-enum probe filter also selected scene visual geoms; the body-ancestry probe supersedes it and exits 0 at visual=19 collision=42 bad=0.
  - A direct system-Python Ruff invocation could not import Ruff; the repository gate with pinned Ruff 0.15.20 is authoritative and passes.
scope_boundary:
  - This terminal result validates robot visual/collision geom typing, executable mesh loading, existing table/cup stability gate, and fresh GUI appearance only.
  - It does not validate MoveIt execution, contact calibration, grasp success, or robot closed-loop hold. The live joint-state stream still reports nonzero instantaneous velocity and is not used as a stability claim here.
preservation:
  - src/so101_gazebo_demo_py status and diff are empty.
  - src/so101_mujoco_demo_py/mjcf/assets status is empty; ai-station workspace mesh locations and bytes are unchanged.
  - Existing Task 13 and EXP-057 unstaged paths remain preserved; index remains empty.
decision: KEEP EXP-058 VALID for the visual repair. Leave the source-matching domain-138 MuJoCo GUI running for user review; do not send actions or infer Task 13 success.
```

## Checkpoint CP-093

```yaml
checkpoint_id: CP-093
last_valid_experiment: EXP-058
current_experiment: EXP-057 remains RUNNING under its separate observable-motion criterion
current_hypothesis: The spherical-robot visual defect is fixed at the executable geom-type boundary. Any remaining joint drift/hold behavior is a separate control/contact task and must not be hidden inside the visual repair.
working_tree_status: HEAD 997e8ed95100e4097744c92f1b065613ab390220; index empty; preserved Task 13/EXP-057 dirty state plus EXP-058 test/MJCF/ledger changes remain unstaged; protected Gazebo and mesh-asset statuses are empty.
owned_processes: Source-matching visualization-only domain-138 stack remains live at launch PID/PGID 1984990 and ros2_control_node PID 1984999 in retained tmux so101-mujoco-gui:0.0; no action goal was sent.
confirmed_conclusions:
  - Explicit type="mesh" is necessary and sufficient to replace the robot spheres with the already-present detailed ai-station worktree meshes.
  - Visual and collision geometry retain the same authoritative paired instance structure; all 61 compiled robot geoms are mesh enum 7 with valid data ids.
  - Fresh CUA visual evidence satisfies the user-requested robot visual repair and shows the mounted base plus complete detailed arm.
open_risks:
  - EXP-057's controller-driven observable-motion criterion is not terminalized by a no-action visual repair.
  - Live closed-loop joint hold remains unqualified and should be diagnosed separately from visual geometry.
next_command: NONE for visual geometry. Keep the GUI available for user inspection and await direction before any action, contact calibration, or hold diagnosis.
```

## EXP-058 Final Verification Addendum

```yaml
final_verification:
  - Fresh no-action CUA snapshot s0296 again shows the same complete detailed mechanical robot, mounted base, pedestal, table, and open cup after more than 220000 simulation steps.
  - Full package verification with pytest cache disabled is 207 passed, 3 skipped; Ruff remains clean with 67 files already formatted.
  - Source and installed robot MJCF SHA-256 remain identical at cf888f91218deaef6b5d394ab6ace0cd3a9cc9b5b2e9a2fdc5ce1423503253bd.
  - Protected Gazebo and MuJoCo mesh-asset statuses remain empty; diff-check passes.
fresh_cua_evidence: /tmp/so101-debug-mujoco-visual-parity-20260811/exp058-cua-final.png
fresh_cua_sha256: ab55c52a4eef21bdbd6416dffc676ff1a243a9d83ed7b0d6be200172b6b893df
invalid_instrumentation_addendum:
  - One final direct pytest rerun created src/so101_mujoco_demo_py/.pytest_cache; the repository isolation test correctly rejected that ignored runtime artifact on the next invocation.
  - The task-created cache was moved intact to /tmp/so101-debug-mujoco-visual-parity-20260811/pytest-cache-final-invalid. The authoritative rerun used -p no:cacheprovider and passed 207/3 without recreating source-tree cache.
decision: EXP-058 remains VALID; no production source changed after the qualified mesh-type fix.
```

## Experiment EXP-059

```yaml
experiment_id: EXP-059
prior_experiment: EXP-058 VALID
status: PLANNED
lifecycle: REUSE_STACK for read-only ROS observation; FULL_RESTART only after a qualified production fix
hypothesis: The visible non-stationary arm at Gazebo home q1..q5=0 is caused either by newly executable robot mesh contacts at the home pose or by an underdamped high-gain position actuator/control boundary; a contact-aware qpos/qvel envelope and one evidence-only collision-disabled A/B will identify the first divergence before any controller tuning.
prediction:
  - Baseline q=0 stepping or the live ROS stack will show a bounded/non-bounded robot joint envelope and identify whether contacts are present while the arm departs home.
  - If contacts are causal, an evidence-only copy with only robot collision participation disabled will remove the joint motion without changing visual meshes, actuator gains, timestep, gravity, or initial qpos.
  - If motion persists without contacts, actuator/control-loop characterization must precede any production gain change.
single_variable: Diagnostic A/B changes only robot collision contype/conaffinity in an evidence-only temporary MJCF copy; production MJCF remains unchanged until the causal branch is proven.
gazebo_home_contract:
  arm_q1_to_q5_rad: [0, 0, 0, 0, 0]
  reset_q6_rad: 0
  moveit_gripper_home_q6_rad: -0.059600220867817
stability_success_criteria:
  - At the selected Gazebo-aligned initial pose, every arm joint position has a final five-second peak-to-peak envelope <= 0.001 rad and absolute velocity <= 0.01 rad/s after settling.
  - No unexplained position drift, high-frequency limit cycle, NaN, or controller transition occurs.
  - A fresh CUA observation shows a visually stationary detailed arm across two separated snapshots.
failure_criteria:
  - Any joint exceeds the stability envelope under valid provenance, or the GUI/control stack exits.
invalid_criteria:
  - Stale install, wrong ROS domain, action contamination, direct state write, unbounded process ownership, or changing more than the declared A/B variable.
follow_on_gate: Only after stability succeeds, set the robot to Gazebo home, start the qualified MoveIt composition, plan and execute TCP to the Gazebo grasp pose, then verify controller success and final TCP/joint error. No grasp close or contact-success claim is included.
safety_contract: Simulation only; no hardware, teleport/direct qpos writes, weld, equality, adhesion, mocap following, broad process kill, or action before stability qualification.
evidence_root: /tmp/so101-debug-mujoco-jitter-20260811
provenance:
  source_commit: 79effd9
  install_overlay: /tmp/so101-debug-mujoco-visual-parity-20260811/install until a fresh fix build is required
  runtime_executable: /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 138 for the existing visualization-only stack
decision: PENDING; diagnostic preregistration only.
```

## Experiment EXP-059 Terminal Result

```yaml
experiment_id: EXP-059
status: VALID
terminal_result: PASS
root_cause:
  - At Gazebo home q1..q6=0, the compiled MuJoCo model generated three base/shoulder contacts with penetration depths 0.022401 to 0.027882 m.
  - Those contacts drove joint 1 to 1.238513 rad with 19.7272 rad/s residual velocity and a 0.279879 rad final-five-second envelope while the actuator saturated at -3.35.
causal_ab:
  - An evidence-only collision-disabled robot copy made all six final-five-second envelopes zero while retaining the cup/table contact.
  - A narrower evidence-only copy excluding only body pair base/shoulder produced the same zero-envelope result and retained cup/table collision participation.
production_fix:
  - Add one explicit MuJoCo contact exclusion for the fixed base/shoulder body pair; do not disable global robot collision and do not change gravity, gains, timestep, visual geometry, or initial positions.
  - Extend the task-scene contract/checker with final-five-second robot position and velocity gates.
verification:
  targeted_test: 4 passed
  full_pytest: 207 passed, 3 skipped
  ruff: All checks passed; 67 files already formatted
  isolated_build: two packages finished
  production_checker: all six position envelopes exactly 0 rad; maximum absolute joint velocity approximately 1e-17 rad/s
  live_ros_window: 501 samples over 4.99976 s; all six position envelopes exactly 0 rad; maximum absolute velocity 1.7069e-17 rad/s
  cua_observation: two CUA-only screenshots five seconds apart show the same detailed arm; robot-region comparison differs by only 3 of 220000 pixels
evidence:
  root: /tmp/so101-debug-mujoco-jitter-20260811
  production_checker: production-green-10s.json
  live_ros_window: live-stability-window.json
  cua_frames: [cua-stable-1.png, cua-stable-2.png]
  tests: [exclude-red.log, full-pytest.log, ruff.log, rebuild.log]
runtime:
  ros_domain_id: 138
  simulation_session_id: exp059-stable-home
  launch_pid_pgid: 2034111
  ros2_control_pid: 2034128
  install_overlay: /tmp/so101-debug-mujoco-jitter-20260811/install
gazebo_home_observed_q1_to_q6_rad: [-2.646e-10, 0.000630961, 0.000535699, 0.000124815, 1.588e-07, -7.081e-06]
scope_boundary: This validates stationary closed-loop hold at the Gazebo reset pose and the causal contact fix. It does not yet validate MoveIt planning/execution, grasp closure, or physical contact success.
decision: KEEP VALID; proceed only to the separately preregistered TCP plan-and-execute check.
```

## Experiment EXP-060

```yaml
experiment_id: EXP-060
prior_experiment: EXP-059 VALID
status: PLANNED
lifecycle: REUSE qualified domain-138 MuJoCo runtime; add one task-owned move_group process without restarting simulation
hypothesis: With the base/shoulder contact defect removed, MoveIt can generate a pose-constrained trajectory from the Gazebo reset pose to the TCP pose corresponding to the unchanged Gazebo DESCEND final arm posture, and ros2_control can execute that trajectory without drift or controller failure.
start_contract:
  source: protected Gazebo initial_positions.yaml and home state
  arm_q1_to_q5_rad: [0, 0, 0, 0, 0]
  reset_q6_rad: 0
target_contract:
  source: identical Gazebo and MuJoCo light_cup_wall_pick.yaml DESCEND final waypoint
  arm_q1_to_q5_rad: [-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465]
  tcp_pose: compute once through the live MoveIt /compute_fk service from the exact target joints, then freeze it before planning
  pose_constraint: world frame, so101_tcp link, box half-width 0.0005 m per axis, orientation tolerance 0.01 rad per axis
single_variable: Commanded arm target changes from Gazebo home to the frozen Gazebo grasp TCP pose. q6 remains at reset value and no cup/contact/grasp-close action is sent.
procedure:
  - Confirm fresh joint state is still inside the EXP-059 home and stability gates.
  - Start one domain-138 move_group against the already running qualified MuJoCo/RSP/controller stack.
  - Compute and record target FK; submit a plan-only MoveGroup pose goal with the current live state.
  - Require successful nonempty plan before one bounded ExecuteTrajectory request.
  - Observe fresh final joint state and TF, then measure a post-execution five-second stationary window.
success_criteria:
  - MoveIt planning error code 1 and nonempty trajectory.
  - ExecuteTrajectory error code 1 with terminal action status SUCCEEDED.
  - Final TCP translation error <= 0.002 m and quaternion angular error <= 0.02 rad from the frozen target.
  - Final joint state is finite; the arm remains within 0.01 rad of the exact Gazebo target joints, or an alternate IK solution is accepted only if the TCP thresholds pass and MoveIt reports success.
  - Post-execution five-second arm position envelope <= 0.001 rad and absolute velocity <= 0.01 rad/s.
failure_criteria:
  - Planning/execution error, empty trajectory, stale state, threshold violation, controller transition, NaN, or runtime exit.
invalid_criteria:
  - Wrong ROS domain/overlay, direct qpos write, a second simulation/controller stack, missing source/target provenance, or unbounded process ownership.
safety_contract: Simulation only; no hardware, no gripper close, no object teleport, no weld/equality/adhesion/mocap following, and no physical-grasp claim.
evidence_root: /tmp/so101-debug-mujoco-tcp-20260811
decision: PENDING; preregistration only, before starting move_group or sending any plan/action.
```

## Experiment EXP-060 Terminal Result

```yaml
experiment_id: EXP-060
status: VALID
terminal_result: PASS
runtime:
  ros_domain_id: 138
  simulation_launch_pid_pgid: 2034111
  ros2_control_pid: 2034128
  move_group_launch_pid_pgid: 2049496
  move_group_pid: 2049562
  simulation_session_id: exp059-stable-home
  install_overlay: /tmp/so101-debug-mujoco-jitter-20260811/install
  controllers_after_execution: [arm_controller active, gripper_controller active, joint_state_broadcaster active]
start_state:
  joints_q1_to_q5_rad: [-2.646255564896834e-10, 0.0006309607155470753, 0.0005356994435149631, 0.00012481540248078117, 1.5882302354461913e-07]
  max_abs_error_from_gazebo_home_rad: 0.0006309607155470753
  max_abs_velocity_rad_s: 1.7069348527116118e-17
target:
  gazebo_descend_joints_q1_to_q5_rad: [-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465]
  frozen_fk_tcp_xyz_xyzw: [0.02067668378158652, -0.2628210212382375, 0.20063061058386278, -0.010265991324917133, -0.010262986627481915, -0.7067526865362342, 0.7073117563008668]
planning:
  group: arm
  link: so101_tcp
  constraint: world-frame position box plus quaternion orientation constraint
  action_status: SUCCEEDED
  moveit_error_code: 1
  trajectory_points: 50
execution:
  action_status: SUCCEEDED
  moveit_error_code: 1
  controller_log: arm_controller successfully finished; trajectory execution completed SUCCEEDED
final_state:
  joints_q1_to_q5_rad: [-0.001833389268777149, 0.4761581623857801, 0.21371631761742924, 0.8508522630334032, 0.004561491804273007]
  max_abs_joint_error_from_gazebo_target_rad: 0.0040701126615967365
  tcp_xyz_xyzw: [0.02115245801016753, -0.2630700124327577, 0.20002946577425498, -0.010647133309820585, -0.010618923307277425, -0.7047598711769995, 0.7092865436469642]
  tcp_translation_error_m: 0.0008060600558574085
  tcp_orientation_error_rad: 0.005707210798801107
post_execution_stability:
  samples: 503 over five seconds
  max_joint_position_envelope_rad: 0.000052858921871623554
  max_abs_joint_velocity_rad_s: 0.001183125091727367
visual_evidence:
  source: ai-station CUA get_window_state, session exp060-grasp
  screenshot: /tmp/so101-debug-mujoco-tcp-20260811/cua-grasp.png
  screenshot_sha256: b5f191bff2a2e0e9d601c6d37541ce80414cb911542ba3e54266dd4be72003c0
  observation: Detailed SO-101 arm is visibly in the cup-side grasp posture; base and mesh visuals remain present.
evidence:
  result: /tmp/so101-debug-mujoco-tcp-20260811/exp060-result.json
  result_sha256: 5e53ad0068fbe33607f0eebf96fe2172c14b90c152608a4a5211079cda39e146
  move_group_log: /tmp/so101-debug-mujoco-tcp-20260811/move-group.log
scope_boundary:
  - This validates the MoveIt pose-constrained arm plan, ExecuteTrajectory path, arm_controller, and MuJoCo ros2_control closed-loop hold.
  - q6 remained at reset, the gripper was not closed, and no grasp/contact/lift success is claimed.
  - The configured KDL solver uses position_only_ik, but the MoveGroup request included an independent orientation constraint and the measured final FK passed the preregistered 0.02 rad orientation threshold.
decision: KEEP VALID; EXP-059 jitter fix and EXP-060 MoveIt/ros2_control execution qualification both pass.
```

## Checkpoint CP-094

```yaml
checkpoint_id: CP-094
checkpoint_time: 2026-08-11T19:45:43+08:00
last_valid_experiment: EXP-060
current_hypothesis: A fresh pose-constrained calibration approach can retain the EXP-059 stable-home and EXP-060 TCP orientation boundaries while preventing the early one-sided contact and cup sweep seen in EXP-055.
working_tree_status: HEAD 1548acb20a2bd376e1bbe867603d824d26ddfb21 on codex/so101-mujoco-ros2; index empty; exactly the three intentional Task 13 drafts are untracked; protected src/so101_gazebo_demo_py diff from d300e7a41fb274d6d7e120699b7040666ea61904 and protected-tree status are empty.
owned_processes: NONE for this Task 13 continuation; no stack, parameter change, GUI action, reset, or process cleanup has occurred.
preserved_processes: All pre-existing sessions and processes are preserved, including codex, codex-cua, codex-teleop, kimi, so101-mujoco-gui windows 0-2, so101-phy5-v2-r0, so101-py-qual, domain-189 Gazebo/MoveIt/RViz, domain-138 move_group PID 2049562, and the domain-139 MuJoCo camera stack with launch PID 2566866, robot_state_publisher PID 2566877, and ros2_control_node PID 2566878.
repository_provenance:
  head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  implementation_baseline: 100880a55fd3fee5fbc1930f293faeb444da9282
  origin_main: c6982116d79c834de60b21d9e324a449a569a9c9
  origin_branch: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  merge_base_with_origin_main: d300e7a41fb274d6d7e120699b7040666ea61904
  dependency_gitlink_and_checkout: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
  dependency_release: so101-0.0.3-r2
draft_sha256:
  contact_calibration_yaml: 570e38b24bf2b8c339757ccaf1e9d0121bededf2beb375aad8af80978b549681
  analyze_contact_calibration_py: 1c259364e1c921fcfda377ab51dc30aa995ecff37881ddbd7f3b213f7589e891
  test_contact_calibration_contract_py: aeb7ea66e702f5931713163b022b58100227a85b7a025d825fe380613452287b
fixed_input_sha256:
  scene_xml: a87fb09459a75eb58d1077659fd67c3b8250226e8b22e05141c470a0423d5d28
  so101_xml: cf888f91218deaef6b5d394ab6ace0cd3a9cc9b5b2e9a2fdc5ce1423503253bd
  model_parity_yaml: a787213d6c156581b7792d50146346c825fa7145a056242a01da802495a00e43
  mujoco_plugins_yaml: dee81a0bd4c8eff0936662f7c256c812aeb07e9eccc4200c9093b1defc0cf8e3
  ros2_controllers_yaml: 499d471acb93ede255199ac6f220fbff39ae2f01f2277eed8e9967230ebbf16a
  dependency_lock_yaml: 2df6e17593d9246be661365d7666994a218cc9fdfbae0c5535aecfa233e2a021
confirmed_conclusions:
  - EXP-055 is a VALID behavioral failure of the old joint-space descent: 14.8177 mm pre-close cup displacement, 24.8491 N peak force, and zero bilateral stable-hold samples. Blind joint-waypoint tuning is disproven.
  - EXP-055 contact observations cannot calibrate the current model because EXP-057/EXP-058 subsequently replaced and qualified executable geometry; a new fixed-fingerprint matrix is mandatory.
  - EXP-058 restored executable mesh geometry, EXP-059 qualified stable Gazebo-home closed-loop hold, and EXP-060 qualified pose-constrained MoveIt execution to the cup-side TCP target without closing q6 or claiming contact/grasp success.
  - The three preserved drafts are not an approved policy: they contain placeholder hashes, empty distributions/confusion cells, and fixed 0.9/1.1 multipliers. They must be hardened with RED/GREEN tests before collection.
  - moveit launch-directed shutdown exit -11 remains an explicitly deferred lifecycle defect. Task 13S, Task 14, and Task 15 remain blocked behind the mandatory Task 13 threshold-approval stop.
  - Repository layout contains no moveit-demo/AGENTS.md and no nested AGENTS.md; the root AGENTS.md is the only repository instruction file present.
disproven_routes:
  - Reusing old-geometry force/distance samples or other_object_contacts as fingertip calibration evidence.
  - Continuing the EXP-055 joint-space waypoint ladder or manufacturing separation with fixed quantile multipliers.
open_risks:
  - No bounded collector, current-fingerprint seven-regime matrix, classification report, or safe threshold proposal exists yet.
  - Domain 138 and 139 are occupied by preserved pre-existing processes; every Task 13 live experiment must use a separately proven empty domain and exact ownership.
  - The historical EXP-057 record was never explicitly terminalized, while its earlier owned runtime no longer exists; this checkpoint does not rewrite that history or count it as current Task 13 evidence.
evidence:
  - /tmp/so101-debug-mujoco-task13-4iKEMQVr/baseline-provenance.txt (sha256 188feb71b2be0e45a83e1a227ec2ab3d8630890d811345c52efebc4bfeba140f)
  - /tmp/so101-debug-mujoco-task13-4iKEMQVr/input-hashes.txt (sha256 7a0f420f3d853c2d78fbe8d95787a89df3bfca22e36cfb21fac6086a3c9a11d0)
  - /tmp/so101-debug-mujoco-task13-4iKEMQVr/process-domain-inventory-v3.txt (sha256 96f626f0659c503e743293a652639dde23cf618c3b139bc4a0da2e33e76bb42d)
next_experiment: EXP-061, the first bounded fixed-geometry no-contact pose-approach qualification after Tasks 13.1-13.3 and isolated build provenance pass.
next_command: Extend test_contact_calibration_contract.py first and capture the required Task 13.1 RED before changing production analyzer/configuration behavior.
```

## Experiment EXP-061

```yaml
experiment_id: EXP-061
prior_experiment: EXP-060 VALID
status: PLANNED
lifecycle: FULL_RESTART
ownership: proven-empty ROS domain 140; only the exact tmux session and process group created for EXP-061 are owned
hypothesis: The fixed-geometry MuJoCo stack can start at the EXP-059 stable q1..q5=0 home, pre-open q6, then execute the new world/so101_tcp pose-constrained pre-grasp and axial descent while physics remains unpaused, without early fingertip contact, forbidden robot/table contact, cup displacement beyond 0.003 m, or force beyond the inherited 11.60 N diagnostic abort boundary.
prediction:
  - The isolated stack reaches active joint_state_broadcaster, arm_controller, and gripper_controller with session task13-exp061 and reset epoch 0.
  - Pre-open reaches q6=0.465038 rad without arm motion or cup displacement.
  - Both pose plans are nonempty, use the frozen EXP-060 orientation, and have fresh plan-to-execute starts; at most one replan is permitted per phase.
  - Sampled FK for the descent is axially monotonic and remains within the 0.003 m lateral corridor.
  - ExecuteTrajectory succeeds for pre-grasp and descent, MuJoCo evidence remains unpaused and in one session/reset, fingertip contact stays empty, and cup displacement stays at or below 0.003 m.
single_variable: Relative to EXP-060, the commanded path changes from one direct frozen grasp-pose move to the production Task 13 two-phase pose-constrained pre-grasp plus axial descent derived from the current cup pose; model, dependency, controller/dynamics, q6 pre-open target, orientation, and safety bounds remain fixed.
source_provenance:
  head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  source_manifest_sha256: e4c9b90d71405d8473950bbe78ea3a4cde944abcfd6cfebfd552011f1448c8f7
  model_sha256: a87fb09459a75eb58d1077659fd67c3b8250226e8b22e05141c470a0423d5d28
  config_sha256: a787213d6c156581b7792d50146346c825fa7145a056242a01da802495a00e43
  dependency_commit: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
  fork_library_sha256: e42731cc13a522c19ea2f7049b0e43d2e08e8b4280f4333a79053ef962a93e1a
  fork_node_sha256: 9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e
  isolated_overlay: /tmp/so101-debug-mujoco-task13-4iKEMQVr/task13-overlay/install
  isolated_build_log_sha256: ae932e59b9dc4159bb93f4f1d2453aaecc71214c934dabe053873e4c96ed9a42
  overlay_provenance_sha256: c37aa97b499a7f5530912c79c17a17dbc2defeff279e2636676fd962464e162b
experiment_adapter:
  launch_sha256: e06fd71b551ffce68c3066f54c8a225a2b82fce4be74a9907d2a6c53cfc0b7ab
  runner_sha256: 7eadfe2938ee894a2b0cc2fb76794bc40a392b5514efce3bfc6a23d23da51409
domain_proof: ROS domains 140 through 144 each had empty no-daemon node discovery and no readable process environment declaring that domain; domain 140 selected.
exact_commands:
  stack: ROS_DOMAIN_ID=140 ROS_LOCALHOST_ONLY=1 ros2 launch /tmp/so101-debug-mujoco-task13-4iKEMQVr/exp061_stack.launch.py
  runner: ROS_DOMAIN_ID=140 ROS_LOCALHOST_ONLY=1 python3 /tmp/so101-debug-mujoco-task13-4iKEMQVr/run_exp061.py
success_criteria:
  - Runner status VALID, both phases complete, execution results succeed, and replan count is at most 2 total.
  - Final evidence remains session task13-exp061/reset 0 and paused false with zero fingertip/forbidden contacts.
  - Cup displacement from the frozen initial pose is at most 0.003 m and maximum observed force is at most 11.60 N.
failure_criteria: Any planning/execution/FK error, empty or invalid path, exhausted replan, early contact, displacement/force abort, paused physics, stale state, or controller/runtime exit is a VALID behavioral failure and stops matrix collection.
invalid_criteria: Provenance mismatch, wrong domain/session/reset, stale overlay, missing atomic evidence, unowned process contamination, direct state write, hidden constraint, or changing another active variable.
safety_contract: Simulation only; no hardware, pause, StepSimulation, direct qpos/qvel write, set-pose, teleport, weld/equality/adhesion/mocap following, or gripper close.
evidence_root: /tmp/so101-debug-mujoco-task13-4iKEMQVr
decision: PENDING; preregistration completed at 2026-08-11T20:13:57+08:00 before stack start or parameter/action change.
```

## Experiment EXP-061 Running Transition

```yaml
experiment_id: EXP-061
status: RUNNING
transition_time: 2026-08-11T20:15:19+08:00
provenance_verified_before_action:
  ros_domain_id: 140
  simulation_session_id: task13-exp061
  tmux_session: so101-task13-exp061
  owned_pgid: 2670511
  launch_pid: 2670579
  robot_state_publisher_pid: 2670607
  ros2_control_pid: 2670608
  move_group_pid: 2670612
  ros2_control_executable: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/lib/mujoco_ros2_control/ros2_control_node
  ros2_control_executable_sha256: 9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e
  ament_prefix_order: [/tmp/so101-debug-mujoco-task13-4iKEMQVr/task13-overlay/install/so101_mujoco_demo_py, /tmp/so101-debug-mujoco-task13-4iKEMQVr/task13-overlay/install/so101_mujoco_support, /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install, /opt/ros/jazzy]
  controllers: [joint_state_broadcaster active, arm_controller active, gripper_controller active]
  stack_log_sha256_at_transition: 661a4aad5af9a0f4c43081cad197682a481d1a8520be080a8566eda5b56a0f56
action_state: No pre-open, planning request, or execution action had been sent when this transition was recorded. The next and only action command is the frozen EXP-061 runner.
```

## Experiment EXP-061 Terminal Result

```yaml
experiment_id: EXP-061
status: VALID
terminal_result: FAIL
terminal_time: 2026-08-11T20:16:00+08:00
observed_result:
  - The owned stack and all three controllers were ready with exact provenance. Gripper pre-open completed successfully at q6=0.465038 rad.
  - Initial arm error from q1..q5=0 was at most 0.001080 rad and maximum arm speed was approximately 2.6e-17 rad/s. Physics was unpaused, session/reset were task13-exp061/0, fingertip and forbidden contacts were empty, and table-support force was approximately 0.196 N.
  - Cup position changed only about 4e-9 m through pre-open. No arm ExecuteTrajectory goal was sent.
  - The first pre-grasp GetMotionPlan request returned MOVEIT_PLAN_FAILED; MoveIt's exact terminal error was START_STATE_INVALID before any trajectory existed.
  - The runner therefore completed zero phases with zero replans and failed closed. Final cup/contact/session/reset/paused evidence remained safe and valid.
acceptance:
  controller_result: PREOPEN_SUCCEEDED; ARM_NOT_SENT
  plan_result: START_STATE_INVALID
  trajectory_points: 0
  early_fingertip_contacts: 0
  forbidden_contacts: 0
  cup_displacement_m: approximately 4e-9
  maximum_observed_force_n: approximately 0.1964
  physics_paused: false
  provenance_valid: true
evidence:
  result: /tmp/so101-debug-mujoco-task13-4iKEMQVr/exp061-result.json
  result_sha256: 4dd866be8e31697f3ec768af876b10a2db7efba8c2b983c45a6138d7771826d4
  runner_log: /tmp/so101-debug-mujoco-task13-4iKEMQVr/exp061-run.log
  runner_log_sha256: 137d8097368cb024dfd9c1c356ad4c1ddaa06d6f3c5612a9982e83acc6fc7bfc
decision: KEEP VALID as an evidence-valid behavioral failure. Do not collect the seven-regime matrix. Perform read-only state-validity diagnosis before deciding whether one single-variable follow-up is justified.
```

## Experiment EXP-062

```yaml
experiment_id: EXP-062
prior_experiment: EXP-061 VALID behavioral failure
status: PLANNED
lifecycle: REUSE_STACK
hypothesis: EXP-061 failed because its explicit MoveIt start RobotState contained q1..q5 but omitted the independently pre-opened q6; supplying the exact current q1..q6 while leaving planning_group=arm will make the unchanged two-phase pose approach plan from the state that MoveIt's read-only validity service has proven valid.
diagnostic_basis:
  - EXP-061 returned START_STATE_INVALID with an explicit q1..q5-only start and sent no arm trajectory.
  - A subsequent read-only /check_state_validity call on the same stack with current q1..q6, including q6=0.4650347488, returned valid=true with zero contacts and zero cost sources.
  - The existing working EXP-060 pattern used a complete current robot state for pose planning.
single_variable: The pose request start RobotState changes from current q1..q5 only to current q1..q6; planning group arm, target derivation, pre-grasp/contact offsets, orientation, tolerances, model, dependency, controllers, session/reset, and safety bounds are unchanged.
tdd_evidence:
  red_sha256: 998ab9c685d48f96c7fdaa8c595b16c872f19c21c8524c7c05fbfd57530edd73
  green_sha256: 8a2a1da34fd240a2e0198a96637ecd1297d0a9e5f272f0ef221977101ad3ee31
provenance:
  source_head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  corrected_motion_module_sha256: f09895138a5b3a742e8e2b8257e8962f2e8abb2a3c81b103f37ffab7da251f4b
  corrected_test_sha256: 73c87bb7c5146a6508dbc2ba5b2991820f2b4c7b66eba13a17681715cc468155
  isolated_rebuild_log_sha256: 4ec6b1c83624e9ada9cb06dcfb26eb7d7b7279b224d9fe8f092377d8569d6233
  read_only_state_validity_sha256: 19f3a63e1e7f90a1dbf8cb6ae4fe665baabc50c1cb3e4c62db7371a3212903af
  adapter_sha256: e4021c7993d56f5a10d3b38b32da9920befa8c2baef9063cb30b8ec0165a555a
stack_reuse_contract: Reuse only if PGID 2670511, ros2_control PID 2670608, move_group PID 2670612, domain 140, session task13-exp061/reset 0, controller activity, executable hash, unpaused evidence, q1..q5 stable home, pre-open q6, and zero fingertip/forbidden contact all remain fresh. Otherwise mark INVALID without action.
exact_command: ROS_DOMAIN_ID=140 ROS_LOCALHOST_ONLY=1 python3 /tmp/so101-debug-mujoco-task13-4iKEMQVr/run_exp062.py
success_criteria: Unchanged from EXP-061; both phases must plan and execute with all safety evidence passing.
failure_criteria: Unchanged from EXP-061. A second evidence-valid behavioral failure with no new discriminating evidence triggers checkpoint/stop rather than further tuning.
invalid_criteria: Any stack/provenance/session/reset/controller mismatch or any active-variable change beyond full start-state inclusion.
decision: PENDING; preregistered before EXP-062 action.
```

## Experiment EXP-062 Running Transition

```yaml
experiment_id: EXP-062
status: RUNNING
transition_time: 2026-08-11T20:20:18+08:00
reuse_provenance_verified:
  owned_pgid_alive: 2670511
  ros2_control_pid_alive: 2670608
  move_group_pid_alive: 2670612
  ros2_control_executable_sha256: 9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e
  controllers: [joint_state_broadcaster active, arm_controller active, gripper_controller active]
  simulation_session_id: task13-exp061
  reset_epoch: 0
  paused: false
  arm_q1_to_q5_rad: [-3.6353329156e-09, 0.00107951465, 0.00090670055, 0.00023423788, 3.070742e-07]
  arm_velocity_rad_s: [9.85e-23, -5.04e-17, -1.36e-17, 2.01e-18, -5.78e-21]
  q6_rad: 0.4650347488
action_state: No EXP-062 action had been sent at this transition. The next action is the one frozen runner command.
```

## Experiment EXP-062 Terminal Result

```yaml
experiment_id: EXP-062
status: VALID
terminal_result: FAIL
observed_result:
  - Full current q1..q6 start-state inclusion passed its unit contract but the unchanged first pre-grasp plan still returned START_STATE_INVALID; no arm trajectory or execution goal was produced.
  - Pre-open, stable home, session/reset, unpaused physics, zero fingertip/forbidden contacts, approximately 0.1964 N table-support force, and nanometre-scale cup motion all remained valid.
  - The full-start-state hypothesis is disproven. A read-only TF measurement found the current home TCP quaternion [-0.499444172, -0.499448153, -0.500549705, 0.500556745] differs from the required EXP-060 target quaternion by 1.539548976 rad, far outside the 0.01 rad path constraint.
root_cause: The request applies the final orientation as a path constraint during pre-grasp, so the otherwise state-valid home pose violates the path constraint at time zero. The pre-grasp needs the orientation as a goal constraint while the already-aligned descent retains it as a path constraint.
evidence:
  result_sha256: 389caf85765816df660b44f323bf2d0e52243a411aa039eb6cfa3bbfbb9ea93f
  runner_log_sha256: c46aeb396d25c09df0c7b1f61f504d7a8332446692ff180208ee8b12bc4ddff8
  home_tcp_tf_sha256: f90ff13c602a0235dc90fd07b3fefe08c234a6924ddc11b08840dc674b10af04
decision: KEEP VALID as a second evidence-valid behavioral failure with new discriminating evidence. Permit one TDD-protected constraint-staging follow-up; do not tune target positions or waypoints.
```

## Experiment EXP-063

```yaml
experiment_id: EXP-063
prior_experiment: EXP-062 VALID behavioral failure
status: PLANNED
lifecycle: REUSE_STACK
hypothesis: Treating the frozen TCP orientation as a pre-grasp goal constraint, then applying it as a path constraint only after pre-grasp alignment during descent, will remove the proven invalid-start contradiction while preserving the unchanged orientation/path/safety contract.
single_variable: Orientation constraint staging changes from goal-plus-path for both phases to goal-only for pre-grasp and goal-plus-path for descent. Full q1..q6 start state, targets, offsets, orientation, tolerances, planning group, model, controllers, and safety bounds remain unchanged.
tdd_evidence:
  red_sha256: 5e96ac168b2509379f8501bfb67d461ad0c1e4c1a60b9a5f14417ef2c680b345
  green_sha256: 825c05f5502a5c7e2a42779447b9a47758b55672285cdad29fdacfe8c5acf677
provenance:
  moveit_planning_sha256: 4b4245347b52fae8ec58c401725d88ed10dd94818cac9a48a0288b6aa58091de
  calibration_motion_sha256: c9bf6b6a0c61b679e11b38d4a2826a702c0998f42f4172c2239a294578525470
  moveit_test_sha256: ff61252543c37050be1a679d898ebe7f4e9b7ea3c8df5b1958ab0e38037369cf
  motion_test_sha256: af213cade89016167bce2ffccf4c2a445a73623dee97d27c7501f811cbae5a78
  isolated_rebuild_sha256: 783718bd5a6d8f73c4a007ce84ed641903b12c561f08ed6fe1640783cd3fe5b1
  adapter_sha256: 5ea46baac199fa737327395f384218e2299c8cf041ab5b6cd4bb328a16bbc093
stack_reuse_contract: Identical to EXP-062 and must be reverified before RUNNING.
exact_command: ROS_DOMAIN_ID=140 ROS_LOCALHOST_ONLY=1 python3 /tmp/so101-debug-mujoco-task13-4iKEMQVr/run_exp063.py
success_criteria: Identical to EXP-061, including both completed phases, successful execution, unpaused physics, zero early contacts, and bounded cup/force evidence.
failure_criteria: Any further evidence-valid behavior failure stops approach qualification with a checkpoint; no fourth tuning experiment is authorized.
decision: PENDING; preregistered before action.
```

## Experiment EXP-063 Running Transition

```yaml
experiment_id: EXP-063
status: RUNNING
transition_time: 2026-08-11T20:24:09+08:00
reuse_provenance_verified:
  owned_processes_alive: [PGID 2670511, ros2_control 2670608, move_group 2670612]
  ros2_control_executable_sha256: 9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e
  controllers: [joint_state_broadcaster active, arm_controller active, gripper_controller active]
  simulation_session_id: task13-exp061
  reset_epoch: 0
  paused: false
action_state: No EXP-063 action had been sent when this transition was recorded.
```

## Experiment EXP-063 Terminal Result

```yaml
experiment_id: EXP-063
status: VALID
terminal_result: FAIL
observed_result:
  - Constraint staging removed the EXP-061/EXP-062 invalid-start condition. MoveIt entered goal sampling from the valid current state and repeatedly invoked the position-only KDL IK plugin.
  - No valid goal state could be sampled for the current-cup-derived pre-grasp position with the frozen EXP-060 orientation; MoveIt terminated with GOAL_STATE_INVALID after the configured five-second planning window.
  - No arm trajectory or ExecuteTrajectory action was produced. Pre-open, stable home, unpaused physics, session/reset, zero fingertip/forbidden contacts, approximately 0.1964 N support force, and negligible cup motion remained valid.
acceptance:
  pregrasp_plan: GOAL_STATE_INVALID
  trajectory_points: 0
  completed_phases: 0
  arm_action_sent: false
  safety_abort: false
  provenance_valid: true
evidence:
  result_sha256: 0745c533879ebfde45713de68852dd1f39b38605f00c22ee741b848e3c7bf648
  runner_log_sha256: 17aef583c94a0997dc89cd8cbe0342a6f014e306e8a854a9f66f4c31e2b090ff
decision: KEEP VALID as an evidence-valid behavioral failure. Stop approach qualification with no fourth path/target experiment, no GUI mirror, and no seven-regime matrix collection. Task 13.5 calibration/commit/push and the mandatory threshold-approval packet are not reachable from this failed prerequisite.
```

## Checkpoint CP-095

```yaml
checkpoint_id: CP-095
checkpoint_time: 2026-08-11T20:29:41+08:00
last_valid_experiment: EXP-063
current_hypothesis: The frozen EXP-060 orientation is not reachable at the current-cup-derived Task 13 pre-grasp position under the fixed position-only KDL solver and unchanged model; resolving that conflict requires a newly reviewed plan rather than another unapproved tuning experiment.
working_tree_status: HEAD 1548acb20a2bd376e1bbe867603d824d26ddfb21 on codex/so101-mujoco-ros2; Task 13 implementation, tests, configuration, and this ledger are uncommitted; protected src/so101_gazebo_demo_py tracked diff and normal status are empty.
owned_processes: NONE. The exact Task 13 tmux session so101-task13-exp061 and its owned PGID/PIDs were stopped; ROS domain 140 has no discovered nodes.
preserved_processes: All pre-existing sessions and processes remain preserved, including codex, codex-cua, codex-teleop, kimi, so101-mujoco-gui, so101-phy5-v2-r0, so101-py-qual, so101-teleop-server, domain-189 Gazebo/MoveIt/RViz, domain-138 move_group, and the domain-139 MuJoCo camera stack.
confirmed_conclusions:
  - Task 13.1 strict RED/GREEN produced a fail-closed schema-v1 analyzer and a still-disabled placeholder policy; approved_by_user/enabled remain false and no threshold is approved.
  - Task 13.2 strict RED/GREEN produced a bounded atomic collector using the existing MuJoCo observer/session/reset/sequence contract; partial or stale evidence is rejected and output remains outside the repository.
  - Task 13.3 strict RED/GREEN produced the bounded two-phase pose approach with fresh start states, one replan limit, safety monitoring, and no simulation pause or direct state writes.
  - EXP-061 validly failed at START_STATE_INVALID before any arm action. Read-only state validity isolated the incomplete start-state hypothesis.
  - EXP-062 validly disproved that hypothesis and identified a 1.539548976 rad home-to-target orientation conflict caused by applying the final orientation as a pre-grasp path constraint.
  - EXP-063 validly removed the invalid-start contradiction but failed at GOAL_STATE_INVALID: no reachable current-cup-derived pre-grasp goal was sampled with the frozen orientation. No arm trajectory, contact matrix sample, or GUI evidence was produced.
  - The preregistered Task 13.4 prerequisite therefore failed. A fourth tuning experiment, Task 13.5 matrix collection/calibration, code or documentation commits, push, and the mandatory threshold-approval packet are not authorized or reachable in this run.
  - EXP-057 remains historical and unchanged; this checkpoint does not silently terminalize or rewrite it.
test_contamination:
  - The package-test gate observes four ignored Gazebo pyc files timestamped 2026-08-11T18:51:50+08:00, before CP-094 and this Task 13 run began. Normal Git status and tracked diff remain empty, but the protected nontracked manifest is aaa2030e5a56b6a8ec959a24c1c42dc5afdc5d566e2ccb6eaadd704c0b7b44f6 rather than the recorded 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
  - Even excluding those four conspicuous pyc files yields 0245cca862d4d94585aceb9e41a4b2ba82bcf10931c4e24b2098b4baee088415, proving broader ignored-manifest drift pre-existed this package-test invocation. No protected-tree file was deleted or rewritten in this run; Task 13 tests were run with PYTHONDONTWRITEBYTECODE=1.
verification_state:
  focused_tdd: PASS; all recorded Task 13 RED cases failed for the intended missing behavior and all corresponding GREEN suites passed.
  isolated_build: PASS for so101_mujoco_support and so101_mujoco_demo_py with exact dependency provenance.
  full_package_pytest: 286 passed, 4 skipped, 15 failed after the final package-identity/header corrections; one remaining failure is the protected ignored-manifest gate and fourteen expose the already-present HEAD visual_reference_updates provenance/gate incompatibility. The latter was independently reproduced from clean committed HEAD 1548acb.
  final_offline_gates: Focused Task 13/MoveIt/package-identity/ledger suite 53 passed; Ruff passed with 79 files formatted; git diff --check passed; protected Gazebo tracked diff/status passed; migration isolation failed only at the recorded ignored-manifest mismatch.
evidence:
  root: /tmp/so101-debug-mujoco-task13-4iKEMQVr
  exp061_result_sha256: 4dd866be8e31697f3ec768af876b10a2db7efba8c2b983c45a6138d7771826d4
  exp062_result_sha256: 389caf85765816df660b44f323bf2d0e52243a411aa039eb6cfa3bbfbb9ea93f
  exp063_result_sha256: 0745c533879ebfde45713de68852dd1f39b38605f00c22ee741b848e3c7bf648
  final_process_isolation_sha256: 617d45baac638591a5189f0695e3abf55abfb86818b8ec5a9df7d4d639e69d47
  final_focused_pytest_sha256: e8440f26a8e0998acb9a88b6e2629c9f229c03c8fd16a6213e7d96cf252b84ff
  final_full_pytest_sha256: 9ff69811f24c831d5bed8041e33fdb24a78be4191259db3115e52372fd7da338
  final_migration_isolation_sha256: 0687d85ecf399fd28dfa52094daac4945a680ae9266bbe571987e765d7f5b025
  head_baseline_provenance_repro_sha256: fd98c6341a766d02f6c57dbbd4d890248399026a85b08317d05be08a46a89334
open_risks:
  - The Task 13 approach target/orientation contract is infeasible as currently frozen; no current-fingerprint seven-regime evidence or confusion matrix exists.
  - The protected ignored-manifest and HEAD provenance/isolation-gate mismatches prevent a clean package/migration verification claim and are outside this stopped Task 13 experiment variable.
  - The separately deferred moveit launch-directed shutdown defect remains untouched; Task 13S, Task 14, and Task 15 remain blocked.
next_experiment: NONE. A new user-reviewed plan is required before any target, orientation, solver, waypoint, contact-threshold, or runtime change.
next_command: Stop at the Task 13 approval boundary and report the failed prerequisite; do not commit, push, set approved_by_user/enabled true, start clean-shutdown work, or begin Task 14/15.
```

## Checkpoint CP-096

```yaml
checkpoint_id: CP-096
checkpoint_time: 2026-08-11T21:55:46+08:00
recovery_reason: ai-station reboot after CP-095; user explicitly authorized recovery plus one bounded read-only reachability diagnostic and, only if gated, one motion qualification.
last_valid_experiment: EXP-063
current_hypothesis: A frozen 0/5/10/15/20/25/30/35/40 mm vertical-offset grid at the unchanged EXP-060 TCP orientation can distinguish an unreachable fixed-orientation pre-grasp contract from an offset-specific reachability failure.
host_recovery:
  hostname: AI-STATION-001
  kernel_boot_id: e56cb844-9226-4e5d-89a9-3fe537392975
  boot_time: 2026-08-11T20:43:27+08:00
  observation_time: 2026-08-11T21:55:46+08:00
  tmux_sessions: [codex]
  codex_cua: ABSENT
  relevant_ros_gazebo_moveit_processes: NONE
  checked_ros_domains_with_empty_graph: [0, 138, 139, 140, 141, 142, 143, 144, 189]
repository_provenance:
  worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
  linked_worktree: true
  branch: codex/so101-mujoco-ros2
  head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  origin_branch: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  origin_main: c6982116d79c834de60b21d9e324a449a569a9c9
  merge_base_with_origin_main: d300e7a41fb274d6d7e120699b7040666ea61904
  dependency_gitlink_mode: 160000
  dependency_gitlink_and_checkout: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
working_tree_status:
  tracked_modified:
    - docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
    - src/so101_mujoco_demo_py/config/headless_execution.yaml
    - src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml
    - src/so101_mujoco_demo_py/setup.py
    - src/so101_mujoco_demo_py/so101_mujoco_demo_py/moveit/planning.py
    - src/so101_mujoco_demo_py/test/test_moveit_boundary.py
    - src/so101_mujoco_demo_py/test/test_package_identity.py
  untracked_preserved:
    - src/so101_mujoco_demo_py/config/contact_calibration.yaml
    - src/so101_mujoco_demo_py/scripts/analyze_contact_calibration.py
    - src/so101_mujoco_demo_py/scripts/collect_contact_calibration.py
    - src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration.py
    - src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration_collector.py
    - src/so101_mujoco_demo_py/so101_mujoco_demo_py/motion/calibration.py
    - src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py
    - src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py
    - src/so101_mujoco_demo_py/test/test_contact_calibration_motion.py
  protected_gazebo_tracked_diff: EMPTY
  protected_gazebo_normal_status: EMPTY
  protected_ignored_manifest: Existing mismatch aaa2030e5a56b6a8ec959a24c1c42dc5afdc5d566e2ccb6eaadd704c0b7b44f6 versus recorded 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f; preserved without deletion or workaround.
evidence_recovery:
  prior_root: /tmp/so101-debug-mujoco-task13-4iKEMQVr
  prior_root_status: EVIDENCE_UNAVAILABLE after reboot
  historical_records_retained:
    - EXP-061 result sha256 4dd866be8e31697f3ec768af876b10a2db7efba8c2b983c45a6138d7771826d4
    - EXP-062 result sha256 389caf85765816df660b44f323bf2d0e52243a411aa039eb6cfa3bbfbb9ea93f
    - EXP-063 result sha256 0745c533879ebfde45713de68852dd1f39b38605f00c22ee741b848e3c7bf648
  qualification: Historical ledger summaries remain durable conclusions, but prior raw files and their hashes cannot be reverified on this boot and must not be cited as currently available artifacts.
  new_root: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz
owned_processes: NONE. Every CP-095 runtime PID, process group, tmux session, ROS graph, and /tmp overlay is invalid after reboot and cannot be reused.
preserved_processes: Current Codex tmux session only; no other live tmux or relevant ROS/Gazebo/MoveIt process was observed on this boot.
lifecycle_boundary:
  - REUSE_STACK is prohibited after reboot.
  - Every subsequent live experiment must use FULL_RESTART, a newly proven empty ROS domain, a new simulation session ID, and a newly rebuilt /tmp overlay/evidence root.
  - Old /tmp install paths cannot establish current runtime provenance.
confirmed_conclusions:
  - EXP-061/062/063 are not repeated; their ledger conclusions remain the historical basis for the newly authorized offset-grid diagnostic.
  - EXP-064 is plan/read-only only: no ExecuteTrajectory, gripper action, pause/step, qpos/qvel write, teleport, weld, equality, target, solver, model, dynamics, controller, or contact-threshold change is authorized.
  - EXP-065 is permitted at most once only if EXP-064 finds at least one reachable, state-valid, collision-free, outside-cup/table candidate with positive geometric clearance. Its offset selection rule is the largest qualifying vertical offset.
evidence:
  reboot_repository_inventory: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/reboot-repository-inventory.txt
  reboot_repository_inventory_sha256: c37864669c4d9388669e8528814394d9c52566168ae52deec71f24c8527665f9
  reboot_process_tmux_inventory: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/reboot-process-tmux-inventory.txt
  reboot_process_tmux_inventory_sha256: 4ffee63986f9b054f0aa447e94b1c7ac0443b3fc72ea39bb018a68842775d980
  reboot_ros_graphs: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/reboot-ros-graphs.txt
  reboot_ros_graphs_sha256: 35dea0434eddc18a09bd70acd81b77f1894d6387c537fde975011f80cf38cc60
  reboot_evidence_availability: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/reboot-evidence-availability.txt
  reboot_evidence_availability_sha256: 0b9e1f2b7e260610f8f4f588cc1ce7eed9dc4360740e1ee11f5ec49dfc5c8ae9
open_risks:
  - No EXP-064 overlay, stack, domain, session, grid result, collision-distance evidence, or trajectory exists yet.
  - The committed-HEAD provenance/isolation incompatibility and protected ignored-manifest mismatch remain disclosed baseline failures; they must not be bypassed by deleting ignored protected files.
  - Contact thresholds remain absent, disabled, and unapproved. Clean shutdown, Task 14, and Task 15 remain out of scope.
next_experiment: EXP-064
next_command: Rebuild a fresh isolated /tmp overlay from the exact dirty source and pinned dependency, verify hashes/prefixes, then preregister EXP-064 before starting any stack.
```

## Experiment EXP-064

```yaml
experiment_id: EXP-064
prior_experiment: EXP-063 VALID behavioral failure; CP-096 reboot recovery
status: PLANNED
lifecycle: FULL_RESTART
hypothesis: At the unchanged EXP-060 TCP orientation and fixed current-cup-derived x/y contact target, at least one preregistered positive vertical offset may admit IK, a valid collision-free goal, positive cup/table clearance, positive joint-limit margin, and a nonempty plan even though the former 40 mm pre-grasp failed goal sampling.
single_variable: Vertical offset above the frozen contact target, evaluated on the finite grid [0, 5, 10, 15, 20, 25, 30, 35, 40] mm; no other model, solver, orientation, x/y target, start state, collision geometry, tolerance, planning, controller, dynamics, or threshold input changes.
frozen_inputs:
  contact_target_m: [0.0206766838, -0.2628210212, 0.2006306106]
  tcp_orientation_xyzw: [-0.0102659913, -0.0102629866, -0.7067526865, 0.7073117563]
  start_joint_names: ['1', '2', '3', '4', '5', '6']
  start_joint_positions_rad: [0.0, 0.0, 0.0, 0.0, 0.0, 0.4650347488]
  offset_grid_mm: [0, 5, 10, 15, 20, 25, 30, 35, 40]
  offset_zero_role: Regression point only; never a pre-grasp candidate.
  selection_rule: If one or more positive-offset points satisfy every qualification predicate, select the largest qualifying vertical offset before observing any motion result.
qualification_predicate:
  - IK succeeds and its returned state is valid.
  - Goal-only fixed-orientation planning succeeds with a nonempty trajectory from the identical full q1-q6 start state.
  - The returned endpoint is valid and every locally evaluated IK/trajectory sample is free of self, cup, table, and combined world collision.
  - Minimum unpadded geometric clearance to both cup and table is strictly positive over the evaluated samples.
  - Minimum bounded joint-limit margin is strictly positive.
read_only_boundary:
  services: [/compute_ik, /compute_fk, /check_state_validity, /plan_kinematic_path]
  local_geometry: A temporary non-production MoveIt PlanningScene mirrors the current MJCF cup wall/bottom and table geometry solely for FCL collision/distance evaluation; it does not apply objects to the live scene.
  forbidden_calls: [ExecuteTrajectory, gripper action, controller or arm action, pause, step, qpos write, qvel write, teleport, weld, equality]
  stack: Minimal robot_state_publisher plus move_group only; no MuJoCo, ros2_control, controller, workflow, or execution node.
fresh_runtime:
  ros_domain_id: 145
  ros_localhost_only: 1
  simulation_session_id: task13-exp064-reboot-e56cb844
  tmux_session: so101-task13-exp064
  prestart_graph: EMPTY
provenance:
  source_head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  dependency_gitlink_and_checkout: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
  fresh_overlay_build_sha256: 6b69219b0d8a9788a2796aab2897a18f4bd74f97d4caa0d817f639fc4689bc88
  fresh_overlay_provenance_sha256: 5e7a58e82badb4bb4f3cf061c282cbcb4c68194ca4d4612f5192b77f2e22f926
  diagnostic_launch_sha256: 9c2041490859a86ad727b51816faf53f435e28571c5cb1a6f5f6b5e79ed7f20f
  diagnostic_runner_sha256: 0079e6ffa53ef3ec1923581438e848be4ba42b6490ac5a64d8c9467664c4a0b9
  local_geometry_helper_sha256: abd60df6b90793eb3f44359b78a1e8ee7a998e54051857a77a2d9e4449bc0900
  rendered_urdf_sha256: 82ead9d1716dc43773c2ed2d3c78ee30c7f53a238ab67baa3b08aebc96e7e38d
  helper_rebuild_log_sha256: 89c1695869a0c6b0a0d7f7d97628f4554a0a8c51d7e4a34c48b3f7a03efd0f2e
  empty_domain_evidence_sha256: f7ccb8a1262f798e033b3e6768e97dfbb3cd414acb795f2bc3e81fe31a2fec73
exact_command: ROS_DOMAIN_ID=145 ROS_LOCALHOST_ONLY=1 python3 /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/run_exp064.py --helper /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/reachability_clearance/install/so101_reachability_clearance/bin/reachability_clearance --urdf /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/exp064_robot_description.urdf --srdf /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install/so101_mujoco_demo_py/share/so101_mujoco_demo_py/config/so101.srdf --output /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/exp064-result.json
success_criteria: Terminalize VALID after all nine frozen offsets are evaluated with complete service and local-geometry fields. EXP-065 becomes eligible only if selected_offset_mm is non-null.
failure_criteria: Terminalize VALID with no candidate and stop if selected_offset_mm is null; do not change the grid, orientation, solver, model, x/y target, or waypoint.
invalid_criteria: Missing/mismatched provenance, nonempty prestart graph, incomplete grid, service/runtime corruption, or any forbidden action/state mutation.
decision: PENDING; preregistered before starting the minimal MoveIt stack.
```

## Experiment EXP-064 Running Transition

```yaml
experiment_id: EXP-064
status: RUNNING
transition_time: 2026-08-11T22:09:15+08:00
full_restart_provenance_verified:
  ros_domain_id: 145
  prestart_graph: EMPTY
  tmux_session: so101-task13-exp064
  process_group_id: 95546
  robot_state_publisher_pid: 95632
  move_group_pid: 95633
  runtime_prefix: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  dependency_prefix: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
  observed_nodes: [/move_group, /robot_state_publisher]
  prohibited_runtime_nodes: NONE
  runtime_provenance_sha256: e2e5ad900f508b0c3fd97847846eb77924b2870b3e774cfdc378bcf6791a3d05
action_state: No diagnostic service call had been sent at this transition. MoveGroup exposes its standard actions, but the frozen runner has no action client and calls only the four preregistered read-only/plan services.
```

## Experiment EXP-064 Terminal Result

```yaml
experiment_id: EXP-064
status: VALID
terminal_result: FAIL
terminal_time: 2026-08-11T22:10:59+08:00
grid_complete: true
read_only_contract:
  action_calls: 0
  execute_trajectory_calls: 0
  simulation_state_writes: 0
  runtime_components: [robot_state_publisher, move_group]
observed_result:
  - All nine frozen offsets completed IK, FK, state-validity, goal sampling/planning, local collision/distance, and joint-limit-margin evaluation.
  - Position-only KDL IK returned success and a MoveIt-valid state at every offset, but each independently returned IK state collided with the cup in the exact local cup/table geometry; its orientation error was nonzero because this solver is configured position-only.
  - Goal-constrained planning returned generic failure code 99999 with no trajectory at 0, 5, 10, 15, 25, 30, 35, and 40 mm; MoveGroup logged invalid goal sampling. At 20 mm it returned SUCCESS with 41 points and a valid endpoint.
  - The 20 mm trajectory was nevertheless not collision-free in the frozen cup geometry: six late trajectory samples, indices 33 through 38, placed gripper in plastic_cup collision. Its final sample cleared the cup by 0.0004381571171105936 m, so the path approaches from inside/intersection before ending outside.
  - No offset satisfied the preregistered conjunction of fixed-direction reachability, collision-free state/path, positive cup/table clearance, positive joint-limit margin, and nonempty trajectory. qualified_offsets_mm is empty and selected_offset_mm is null.
offset_results:
  fields: [offset_mm, ik_code, state_valid, plan_code, trajectory_points, self_collision, world_collision, cup_collision, table_collision, minimum_joint_margin_rad, minimum_cup_clearance_m, minimum_table_clearance_m, qualified]
  rows:
    - [0, 1, true, 99999, 0, false, true, true, false, 0.20466149001708223, -1.0, 0.05647541469860941, false]
    - [5, 1, true, 99999, 0, false, true, true, false, 0.1643422187889596, -1.0, 0.06281728900812954, false]
    - [10, 1, true, 99999, 0, false, true, true, false, 0.5169062178240369, -1.0, 0.05206880246936112, false]
    - [15, 1, true, 99999, 0, false, true, true, false, 0.4998865386736273, -1.0, 0.05720111427996215, false]
    - [20, 1, true, 1, 41, false, true, true, false, 0.48713596135634596, -1.0, 0.06233824609061987, false]
    - [25, 1, true, 99999, 0, false, true, true, false, 0.45326380279126677, -1.0, 0.06624211972402426, false]
    - [30, 1, true, 99999, 0, false, true, true, false, 0.4291703409428369, -1.0, 0.07127597103846782, false]
    - [35, 1, true, 99999, 0, false, true, true, false, 0.40866136514295226, -1.0, 0.07630525387350927, false]
    - [40, 1, true, 99999, 0, false, true, true, false, 0.391650099193936, -1.0, 0.08134044712815865, false]
distance_note: The unpadded MoveIt/FCL distance API reports -1.0 for a colliding state; collision flags and contact pairs identify those rows as gripper/plastic_cup intersections rather than positive clearance.
evidence:
  result_sha256: 4896d8b96dc1d89c2484b797ca30770a4effa8a4bca57eb740bc552f4f3758f4
  geometry_query_sha256: e15ba5da5887d004813003a7864f01988e968a8373faec9791d00c37c7104b9f
  geometry_results_sha256: c4594e9c5bf5b3e03f1133b36238de828b512781801455280d2c0b54263b78ef
  summary_sha256: 7a5142f742e961baf87bcfd531b0b453b34950ee03cdb6667f7f5de260d5bc1e
  runner_log_sha256: ce8b054f13820bf702128b6be903be67da5892be04a595b4fb111cecfc2759ae
  stack_log_sha256: f93842d75a27187c749c47a07989250d6123519d7174c1d8740802dac240ba37
  postrun_audit_sha256: e7b099ad73e740a661e93cfa02f74f6e53c5d0f0289f02b2d299aad32d01809d
  poststop_isolation_sha256: b7aaa3cc8d904bf27229b355760aecba4b451ff389ca50c47b6a72ce8532c8dc
decision: KEEP VALID as the complete bounded read-only diagnostic. Stop because there is no qualifying offset; EXP-065, Task 13.5 collection, threshold proposal, commit, and push are not authorized or reachable.
```

## Checkpoint CP-097

```yaml
checkpoint_id: CP-097
checkpoint_time: 2026-08-11T22:11:43+08:00
last_valid_experiment: EXP-064
current_hypothesis: The entire preregistered vertical grid fails the unchanged fixed-orientation, collision-free, positive-clearance approach contract; vertical offset alone cannot qualify the current approach.
working_tree_status: HEAD and origin/codex/so101-mujoco-ros2 remain 1548acb20a2bd376e1bbe867603d824d26ddfb21; Task 13 implementation/tests/configuration and ledger are intentionally dirty and uncommitted. The three user-protected original draft files retain sha256 3b857d9663953a8f41382061b1c068798e3c54bc6d478eceebab0989ae331db1, a03d3d5ef3b00e56d0f33486f4bb52ce5eab0ab16e4701c6462c3cb4367213bf, and de91a4e997c61f068758dbdbb9ba0806405841b053c65913737509b5738663d8.
owned_processes: NONE. The exact EXP-064 tmux session/process group and PIDs were stopped; ROS domain 145 is empty.
preserved_processes: The pre-existing codex tmux session remains; no unrelated session or process was stopped.
confirmed_conclusions:
  - CP-096 validly established reboot recovery, invalidated all old runtime provenance, and required FULL_RESTART.
  - EXP-064 used the freshly rebuilt pinned overlay, a previously empty domain, and only a minimal non-executing MoveIt/robot-model service stack.
  - The frozen nine-point grid is complete. No qualifying positive offset exists; 20 mm alone planned, but its path intersects the cup, while every other point failed goal sampling and every independent position-only IK sample also intersects the cup.
  - The preregistered gate therefore prohibits EXP-065. No production offset selection logic was changed, so no conditional RED/GREEN implementation was entered.
  - Task 13.5 seven-regime collection, disabled threshold proposal, scoped commit, push, and mandatory threshold-approval packet remain unreachable. approved_by_user/enabled remain false.
  - EXP-057 and all prior experiment history remain unchanged; clean-shutdown work and Tasks 14/15 were not started.
test_contamination:
  - The protected ignored Gazebo manifest remains the pre-existing aaa2030e5a56b6a8ec959a24c1c42dc5afdc5d566e2ccb6eaadd704c0b7b44f6 mismatch against recorded 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
  - No protected ignored file was deleted or rewritten to bypass this known package/migration isolation failure. Protected Gazebo tracked diff and normal status remain empty.
verification_state:
  focused_task13: PASS; 52 passed.
  ledger_contract: PASS; 1 passed, 33 deselected.
  ruff: PASS; all checks passed and 79 files already formatted.
  combined_with_repository_isolation: 71 passed, 15 failed. The failures reproduce the previously disclosed protected ignored-manifest mismatch and committed-HEAD visual_reference_updates provenance incompatibility; they are not attributed to EXP-064.
  migration_isolation: EXPECTED BASELINE FAIL with exit 1 at protected nontracked manifest aaa2030e5a56b6a8ec959a24c1c42dc5afdc5d566e2ccb6eaadd704c0b7b44f6 versus 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
  final_boundaries: PASS; git diff check, protected Gazebo tracked diff/status, unchanged local/remote HEAD, disabled/unapproved policy, empty domain 145, and codex-only tmux state.
evidence:
  root: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz
  exp064_result_sha256: 4896d8b96dc1d89c2484b797ca30770a4effa8a4bca57eb740bc552f4f3758f4
  exp064_geometry_results_sha256: c4594e9c5bf5b3e03f1133b36238de828b512781801455280d2c0b54263b78ef
  exp064_stack_log_sha256: f93842d75a27187c749c47a07989250d6123519d7174c1d8740802dac240ba37
  exp064_poststop_isolation_sha256: b7aaa3cc8d904bf27229b355760aecba4b451ff389ca50c47b6a72ce8532c8dc
  final_task13_focused_pytest_sha256: 1a2588935b40290ea4ccca5181db800c9b5b548118f167b1f0f02c3e4c3da2ec
  final_ledger_pytest_sha256: 2778392902065c53a85331e4a8033096dc7d2a046de476a5af3ddc6a27d0e5ca
  final_ruff_sha256: e3e75536809fddead684100d219413a6157dcc009e3a2f510ac2e0f3d1e2307a
  contaminated_combined_pytest_sha256: 9e4d87b470e2c4646bad62029a948f5e4187e127dd6f8b5b2c2587429f911870
  final_migration_isolation_sha256: 0687d85ecf399fd28dfa52094daac4945a680ae9266bbe571987e765d7f5b025
  final_boundary_audit_sha256: 161236bc58503f1580e3c029bac5664dccf569f83959e72ee9199d484298ee06
open_risks:
  - No current fixed-orientation, collision-free, positive-clearance pre-grasp exists on the authorized grid, so no motion qualification or seven-regime data exists.
  - Resolving the geometry conflict would require a new user-reviewed change such as orientation, lateral waypoint, solver/model, or target-contract work; none is authorized here.
  - The protected ignored-manifest and committed-HEAD provenance/isolation incompatibilities remain disclosed baseline failures.
next_experiment: NONE
next_command: Stop and report. Do not execute EXP-065, change approach variables, collect Task 13.5 regimes, commit/push, approve/enable thresholds, start clean-shutdown repair, or begin Task 14/15.
```

## Checkpoint CP-098

```yaml
checkpoint_id: CP-098
checkpoint_time: 2026-08-11T22:58:29+08:00
recovery_reason: User reviewed the mandatory CP-097 stop and supplied a new bounded authorization for EXP-066 read-only contract-layer diagnosis plus only a later, explicitly gated minimal fix.
last_valid_experiment: EXP-064
current_hypothesis: Goal-sampling incompatibility and physical cup intersection are potentially independent failures; they must be separated before selecting an owning layer or changing production behavior.
working_tree_status: Exact CP-097 dirty path set is preserved. HEAD and origin/codex/so101-mujoco-ros2 remain 1548acb20a2bd376e1bbe867603d824d26ddfb21. The protected drafts retain sha256 3b857d9663953a8f41382061b1c068798e3c54bc6d478eceebab0989ae331db1, a03d3d5ef3b00e56d0f33486f4bb52ce5eab0ab16e4701c6462c3cb4367213bf, and de91a4e997c61f068758dbdbb9ba0806405841b053c65913737509b5738663d8.
owned_processes: NONE. Checked ROS domains 0, 138, 139, 140, 145, 146, 147, and 189 are empty; no relevant ROS/Gazebo/MoveIt process exists.
preserved_processes: Existing codex tmux session only; no session or process was stopped.
protected_gazebo_gate: Tracked diff and normal status are empty. Protected files were read only for geometry/TCP parity and remain unmodified.
cp097_readback:
  - EXP-064 result and geometry-result files remain present with their recorded hashes 4896d8b96dc1d89c2484b797ca30770a4effa8a4bca57eb740bc552f4f3758f4 and c4594e9c5bf5b3e03f1133b36238de828b512781801455280d2c0b54263b78ef.
  - No EXP-065, Task 13.5 matrix, threshold approval/enablement, commit, push, clean-shutdown work, Task 14, or Task 15 occurred between CP-097 and this recovery.
new_evidence_root: /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j
evidence:
  recovery_inventory_sha256: 4ff2043331b91c48ed930786b217fbbf824798d2330e8922e07adcd1b8a1e5e2
  recovery_ros_graphs_sha256: c3b7f8c24a80320a776e88f75184131d961458d3a061b300043b1d00d7d59f19
  prestart_isolation_sha256: b12e77db2ba99cb4432d3616cb5cdb39e2bffc3623ca1fa0b857aae8a46d6b13
next_experiment: EXP-066
next_command: Preregister EXP-066 with the frozen full-pose versus position-only goal A/B and static geometry parity evidence, then start only the minimal MoveIt/robot-model service stack on empty domain 146.
```

## Experiment EXP-066

```yaml
experiment_id: EXP-066
prior_experiment: EXP-064 VALID behavioral failure; CP-098 recovery
status: PLANNED
lifecycle: FULL_RESTART
hypotheses:
  H1: The five-DoF arm with position-only KDL IK is incompatible with the production three-axis 0.01 rad orientation pose-goal contract, causing full-pose goal sampling failure.
  H2: Independently of the goal-sampling contract, successful plans to the current pre-grasp/contact x/y/z grid intersect the cup and are unsafe.
  H3: EXP-064 collision findings are false positives caused by a cup/table geometry, frame, TCP transform, or robot-collision-mesh mismatch against current MJCF/URDF/Gazebo reference.
single_variable: Goal constraint representation changes between A=production full position plus three-axis orientation goal and B=the identical position region without an orientation constraint. Target positions, frozen nine-point offset grid, start q1-q6, planning group, solver/config, model, tolerances, planner time, collision evaluator, and geometry remain fixed.
frozen_inputs:
  offsets_mm: [0, 5, 10, 15, 20, 25, 30, 35, 40]
  contact_target_m: [0.0206766838, -0.2628210212, 0.2006306106]
  tcp_orientation_xyzw: [-0.0102659913, -0.0102629866, -0.7067526865, 0.7073117563]
  orientation_tolerance_rad: [0.01, 0.01, 0.01]
  start_joint_names: ['1', '2', '3', '4', '5', '6']
  start_joint_positions_rad: [0.0, 0.0, 0.0, 0.0, 0.0, 0.4650347488]
  planning_attempts_per_mode_per_offset: 1
  allowed_planning_time_s: 5.0
  mode_order_per_offset: [full_pose, position_only]
predictions:
  H1_supported: At least one offset fails A but succeeds B, while direct IK succeeds yet its FK orientation error exceeds 0.01 rad; this localizes the first divergence to goal-contract/solver compatibility rather than raw positional reachability.
  H2_supported: At least one successful A or B trajectory has a gripper/jaw versus plastic_cup collision under the exact unpadded local geometry; planner success remains insufficient for safety.
  H3_supported: Any mismatch is found in cup pose/walls/bottom, table pose/size, world/TCP mapping, or robot gripper/fingertip collision meshes, or fresh collision evaluation does not reproduce the claimed contact under source-faithful inputs.
  H3_disfavored: Current MuJoCo and protected Gazebo cup/table parameters, MuJoCo and protected Gazebo TCP transform, and corresponding robot collision meshes match exactly, and fresh FCL identifies the same robot/cup contact family.
static_geometry_audit:
  - MuJoCo scene and protected Gazebo world both place the cup at [0.02, -0.28, 0.165] and table at [0, -0.20, 0.10].
  - All 12 wall poses/sizes, the cup bottom dimensions, and table dimensions are represented identically after MuJoCo half-size to SDF/FCL full-size conversion.
  - MuJoCo URDF and protected Gazebo xacro both define gripper to so101_tcp translation [0.0214, 0, -0.083949] with zero rotation.
  - Seven fixed-pad, six moving-pad, and seven fixed-finger collision mesh pairs are byte-identical.
  corrected_audit_sha256: 9fb7bea6e499533769cf1a8eeef63c5a0935d33cf2305e0615854f2f2ba59ea0
  correction: Earlier /tmp geometry-static-parity.txt is INVALID only for its fixed-finger subsection because its check used a nonexistent path and printed false MATCH lines; the corrected audit uses collision/fixed_finger_contact and fails closed.
read_only_boundary:
  services: [/compute_ik, /compute_fk, /check_state_validity, /plan_kinematic_path]
  forbidden: [controller calls, actions, ExecuteTrajectory, gripper calls, MuJoCo runtime, pause, step, qpos write, qvel write, teleport, weld, equality, production config change]
  runtime_components: [robot_state_publisher, move_group]
fresh_runtime:
  ros_domain_id: 146
  ros_localhost_only: 1
  simulation_session_id: task13-exp066-contract-diagnostic
  tmux_session: so101-task13-exp066
provenance:
  source_head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  dependency_gitlink_and_checkout: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
  fresh_overlay_build_sha256: 5a3aacaf82ec1bc6948e5634cdbfa492bd848ba4d8aeae0cc28b6fdd2873d2af
  fresh_overlay_provenance_sha256: e90ce72ebb23461f218e7db96d4c44a520c1bac6d1f864ae5006f8b1e286d653
  kinematics_sha256: 7d1854edc8c6e28125fcb92f80641241e828f547a674a94a2c9857b001747d4b
  motion_policy_sha256: b903ff79620f81c9ccafaa5f216fbd4fd263d5b37cb7247ae959605f8c302ae7
  planning_module_sha256: 4b4245347b52fae8ec58c401725d88ed10dd94818cac9a48a0288b6aa58091de
  diagnostic_launch_sha256: 7356ba18b80763dc24e790666d2795e42fd612e1e4a99e2732e15b006a32369b
  diagnostic_runner_sha256: e7557436509bb461c5853d55dbe9c97a8211f9b235d46f56fae25a5457dd294d
  rendered_urdf_sha256: 5f4dd80cee053945879ec5ac5a00437430ff7ed328cef149f4a79300ada056f9
  local_geometry_helper_sha256: abd60df6b90793eb3f44359b78a1e8ee7a998e54051857a77a2d9e4449bc0900
  helper_build_sha256: 86a3e33e917609f4129b5f04f3aa4dd04510551525dfc02859a6bb848f55b6fd
  prestart_isolation_sha256: b12e77db2ba99cb4432d3616cb5cdb39e2bffc3623ca1fa0b857aae8a46d6b13
exact_command: ROS_DOMAIN_ID=146 ROS_LOCALHOST_ONLY=1 python3 /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j/run_exp066.py --helper /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j/helper/install/so101_reachability_clearance/bin/reachability_clearance --urdf /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j/exp066_robot_description.urdf --srdf /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j/overlay/install/so101_mujoco_demo_py/share/so101_mujoco_demo_py/config/so101.srdf --geometry-parity-sha256 9fb7bea6e499533769cf1a8eeef63c5a0935d33cf2305e0615854f2f2ba59ea0 --output /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j/exp066-result.json
success_criteria: All nine offsets complete direct IK/FK and both frozen plan modes with state, trajectory, FK, and local geometry evidence sufficient to decide H1/H2 independently and audit H3.
invalid_criteria: Incomplete grid/mode, provenance mismatch, nonempty prestart graph, runtime contamination, missing geometry evidence, or any forbidden call/state mutation.
decision: PENDING; preregistered before starting the minimal stack or sending a service request.
```

## Experiment EXP-066 Running Transition

```yaml
experiment_id: EXP-066
status: RUNNING
transition_time: 2026-08-11T23:00:10+08:00
full_restart_provenance_verified:
  ros_domain_id: 146
  prestart_graph: EMPTY
  tmux_session: so101-task13-exp066
  process_group_id: 123799
  robot_state_publisher_pid: 123880
  move_group_pid: 123881
  runtime_prefix: /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j/overlay/install
  dependency_prefix: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
  live_kinematics_solver: kdl_kinematics_plugin/KDLKinematicsPlugin
  live_position_only_ik: true
  mujoco_or_controller_runtime: NONE
  runtime_provenance_sha256: bf008cd0c9ee7b65245bcac3bed1cabbec6f383a5da775d988f722aaa322e56f
action_state: No diagnostic service request had been sent at this transition. The frozen runner constructs only GetPositionIK, GetPositionFK, GetStateValidity, and GetMotionPlan clients and contains no action client.
```

## Experiment EXP-066 Terminal Result

```yaml
experiment_id: EXP-066
status: VALID
terminal_result: DIAGNOSED
terminal_time: 2026-08-11T23:01:57+08:00
grid_complete: true
read_only_contract:
  action_calls: 0
  execute_trajectory_calls: 0
  controller_calls: 0
  mujoco_state_writes: 0
observed_result:
  - The live move_group readback confirmed kdl_kinematics_plugin/KDLKinematicsPlugin with position_only_ik=true.
  - Direct IK succeeded at all nine offsets, but FK orientation error ranged from 0.7780211832 to 1.5296967606 rad, always far above the production 0.01 rad tolerance.
  - Full-pose planning succeeded at 5, 10, 15, and 40 mm and failed with code 99999 at 0, 20, 25, 30, and 35 mm. Position-only planning succeeded at all nine offsets. The full-fail/position-success set is [0, 20, 25, 30, 35] mm.
  - Full-pose success is stochastic rather than uniformly impossible: EXP-064 succeeded only at 20 mm, while this fresh FULL_RESTART succeeded at 5/10/15/40 and failed at 20. Goal sampling repeatedly invokes a solver that does not solve orientation and succeeds only when a sampled positional IK state happens to meet the independent orientation constraint.
  - Removing the orientation goal is not a safe fix. Every position-only trajectory intersected plastic_cup; endpoint orientation errors remained approximately 0.77 to 1.52 rad.
  - Full-pose trajectories at 5, 10, and 15 mm also intersected plastic_cup in 7, 6, and 6 samples respectively. The 40 mm full-pose trajectory was the sole collision-free full-pose plan in this run: 43 points, final orientation error 0.0025229242 rad, minimum cup clearance 0.0096339350 m, and minimum table clearance 0.0993070469 m.
hypothesis_decisions:
  H1: SUPPORTED with qualification. The contract is sampling-incompatible and nondeterministic, not mathematically unreachable at every offset.
  H2: SUPPORTED as an independent safety boundary. Eliminating orientation constraints makes every sampled path collide, and some successful full-pose paths also collide. The stronger claim that every full-pose 40 mm approach must collide is disproven by this run.
  H3: DISFAVORED. Corrected static audit found exact source parity for cup/table pose and dimensions, TCP transform, and corresponding robot collision meshes; fresh FCL again reported gripper/plastic_cup contacts. No frame or geometry mismatch was found.
first_bad_boundaries:
  goal_contract: A position-only IK plugin feeds a three-axis 0.01 rad orientation goal sampler, producing nondeterministic goal sampling across identical targets.
  collision_safety: The minimal MoveGroup planning world contains no cup/table collision objects, so planner SUCCESS cannot reject paths that the source-faithful external geometry proves intersect the cup.
conditional_fix_decision:
  - Do not remove orientation constraints; EXP-066 directly disproves that minimal-looking change as safe.
  - Do not automatically change position_only_ik or inject planning-scene geometry in this experiment. Those alter two separate owning layers and require an explicitly preregistered D2 with RED/GREEN contracts and a plan-only validation.
  - Do not execute the collision-free 40 mm sample; it is one stochastic plan, not a repaired deterministic contract.
evidence:
  result_sha256: 8c2f1c1711e4e977185692240484e7b0d3231dd6767c74bb7720dbe88457f5b0
  geometry_query_sha256: 582b671b3b410eba88f7762f9904b77517778a25ccc320a4345781e15c873fae
  geometry_results_sha256: 75a700a711887692702c77ffc5fbbf51815f4d201ddfc698d7d07612a56342d2
  summary_sha256: 19054b7bdfdc812cce39379eabbfa09dc1ae84e03f7083008761e12898f7bb5f
  runner_log_sha256: 53fe97d327fda2d0304d29701e9ef3a25990afa61ff598d06a2a79fea692ba4c
  stack_log_sha256: 3bcd67e9f012ebacc63f38ed78472ffa7a30e5f36c25a5e63d3ed307f8f470a3
  corrected_static_geometry_audit_sha256: 9fb7bea6e499533769cf1a8eeef63c5a0935d33cf2305e0615854f2f2ba59ea0
  corrected_postrun_audit_sha256: cba1c3cd66b14087073c4611a5aaa1b09ffbb597a89dd866d4f161c527abfc6c
  poststop_isolation_sha256: 09a172b85b2a27cc62d43d79383454de9c03ee2a55cfecc4c3a35df6f4ac491d
evidence_corrections:
  - geometry-static-parity.txt sha256 c087935502550283497cbcf50cbaa09bf842b0238ab090fea1c99a9f85946e73 is INVALID for its fixed-finger subsection because the command used a nonexistent path and did not fail its output pipeline; no conclusion uses its false MATCH lines.
  - exp066-postrun-audit.txt sha256 0bab090a2e31eb3938249f12d847db3559df27fefbe9f0d3aa4a12ec0902bc45 is INVALID only for its position-only collision subsection because jq queried the wrong object level. The result and geometry JSON were unaffected; corrected audit cba1c3cd66b14087073c4611a5aaa1b09ffbb597a89dd866d4f161c527abfc6c records six colliding 40 mm position-only samples.
decision: KEEP VALID as the bounded D1 diagnosis. No production fix, action, Task 13.5 collection, threshold change, commit, or push follows without a separately frozen D2.
```

## Checkpoint CP-099

```yaml
checkpoint_id: CP-099
checkpoint_time: 2026-08-11T23:02:25+08:00
last_valid_experiment: EXP-066
current_hypothesis: Two independent owning-layer defects exist: orientation-blind goal sampling is nondeterministic, and the planner lacks an authoritative cup/table collision world. A safe minimal repair cannot be selected by deleting orientation constraints.
working_tree_status: Exact Task 13 dirty path set remains preserved; only this ledger changed during D1. HEAD and origin/codex/so101-mujoco-ros2 remain 1548acb20a2bd376e1bbe867603d824d26ddfb21.
owned_processes: NONE. The EXP-066 tmux session/process group and exact robot_state_publisher/move_group PIDs were stopped; ROS domain 146 is empty.
preserved_processes: Existing codex tmux session remains. No unrelated process/session was stopped.
protected_gazebo_gate: Protected files were only read for parity; tracked diff and normal status remain empty.
confirmed_conclusions:
  - H1 is supported as a stochastic solver/goal-contract mismatch. The same full-pose grid changed successful offsets across EXP-064 and EXP-066, while position-only plans succeeded everywhere and all direct IK orientations missed tolerance.
  - H2 is a distinct safety failure. Planner success alone is unsafe because its live world omits the cup/table; source-faithful local collision checks reject all position-only paths and three of four full-pose successes.
  - H3 is disfavored by exact MJCF/Gazebo/URDF/TCP/mesh parity and reproduced gripper/plastic_cup contacts.
  - A 40 mm full-pose plan can be geometrically safe, but one stochastic plan does not satisfy deterministic qualification and was not executed.
  - Dropping orientation constraints is disproven as a conditional minimal repair. No production file was modified in D1.
  - approved_by_user and enabled remain false; Task 13.5, commit/push, clean shutdown, Task 14, and Task 15 remain untouched.
test_contamination: The existing protected ignored-manifest and committed-HEAD isolation incompatibilities remain unchanged; no protected ignored file was deleted or rewritten.
evidence:
  root: /tmp/so101-debug-mujoco-task13-exp066-C4zQir6j
  exp066_result_sha256: 8c2f1c1711e4e977185692240484e7b0d3231dd6767c74bb7720dbe88457f5b0
  exp066_geometry_results_sha256: 75a700a711887692702c77ffc5fbbf51815f4d201ddfc698d7d07612a56342d2
  corrected_geometry_parity_sha256: 9fb7bea6e499533769cf1a8eeef63c5a0935d33cf2305e0615854f2f2ba59ea0
  exp066_poststop_isolation_sha256: 09a172b85b2a27cc62d43d79383454de9c03ee2a55cfecc4c3a35df6f4ac491d
open_risks:
  - No deterministic orientation-aware goal-sampling contract has been tested.
  - No production planning-scene cup/table collision contract exists in the current approach path.
  - The sole collision-free 40 mm full-pose plan has no repeatability evidence and cannot authorize execution.
next_experiment: NONE
next_command: Await a bounded D2 authorization that freezes one owning layer at a time. Recommended first D2 is temporary orientation-aware IK plan-only diagnosis at the unchanged 40 mm target, followed only if viable by RED/GREEN production configuration work; collision-world integration must remain a separate gated change.
```

## Correction after CP-099: supplemental D1 evidence scope

```yaml
correction_time: 2026-08-11T23:07:56+08:00
applies_to: EXP-066 evidence completeness, not its recorded observations or terminal status
reason: The user's detailed D1 evidence requirements arrived after EXP-066 and CP-099 had already been terminalized. The monotonic ledger therefore does not rewrite EXP-066 history.
preserved_conclusions:
  - EXP-066 remains VALID for its recorded A/B service results, independent whole-path cup/table/self collision flags and clearances, and static MJCF/Gazebo/URDF parity conclusion.
new_limitations:
  - EXP-066 recorded only scalar quaternion orientation error, not per-axis error components or the protected Gazebo approach-axis error.
  - EXP-066 recorded contact pairs/counts, not per-contact penetration depth and the first colliding trajectory index/depth/classification.
  - EXP-066 did not preserve the protected Gazebo waypoint/TCP/approach-axis/touch-link semantics in one explicit read-only evidence artifact.
consequence: EXP-066 cannot by itself gate a production request-expression fix under the new authorization. EXP-067 remains reserved exclusively for the conditional post-RED/GREEN plan-only validation named by the user. EXP-068 is the monotonic supplemental read-only D1 experiment.
```

## Checkpoint CP-100

```yaml
checkpoint_id: CP-100
checkpoint_time: 2026-08-11T23:07:56+08:00
recovery_reason: Read back CP-097 through CP-099 and apply the user's new bounded authorization without silently rewriting the already terminal EXP-066 record.
last_valid_experiment: EXP-066
working_tree_status: The exact CP-099 Task 13 dirty path set and protected draft hashes are unchanged. HEAD and origin/codex/so101-mujoco-ros2 both remain 1548acb20a2bd376e1bbe867603d824d26ddfb21.
owned_processes: NONE. No MoveIt, robot_state_publisher, MuJoCo, ros2_control, RViz, or task runtime is active. Domains 0, 145, 146, 147, 148, and 189 were read as empty before preregistration.
preserved_processes: Existing codex tmux session only; no unrelated session or process was changed.
protected_gazebo_gate: Tracked diff and normal status are empty. Gazebo sources were read only and establish five arm variables 1-5, so101_tcp fixed under gripper at [0.0214, 0, -0.083949], approach-axis validation at 0.08726646259971647 rad, no allowed approach touch pairs, and attachment touch_links [gripper, jaw] only after attachment.
protected_drafts_sha256:
  contact_calibration_yaml: 3b857d9663953a8f41382061b1c068798e3c54bc6d478eceebab0989ae331db1
  analyzer: a03d3d5ef3b00e56d0f33486f4bb52ce5eab0ab16e4701c6462c3cb4367213bf
  contract_test: de91a4e997c61f068758dbdbb9ba0806405841b053c65913737509b5738663d8
evidence:
  root: /tmp/so101-debug-mujoco-task13-exp068-MQn9fJqx
  cp099_readback_sha256: 8941c6abb9864074812e7a56ad8b39636f2ca2b2365a0fb3acc2618e1399840f
  prestart_ros_graphs_sha256: b709f0918c813f8c072aa9f201c836f0eb120423dbae24a03b924f58c7b1c3c0
  gazebo_readonly_contract_sha256: cdeb8f17486f260d966311514f9becc9809722cda5c37f01bbea01bfc83528d0
  frozen_provenance_sha256: 3bb4f2a6a58244f71a5a2ceb10f483fae643bcb7052800f8365159949fc3da1e
next_experiment: EXP-068
next_command: Preregister the supplemental read-only A/B before constructing its temporary contact-detail evaluator or launching the minimal MoveIt stack.
```

## Experiment EXP-068

```yaml
experiment_id: EXP-068
prior_experiment: EXP-066 VALID, with the post-CP-099 evidence-completeness correction above
status: PLANNED
lifecycle: FULL_RESTART
hypotheses:
  H1: Five-DoF position-only KDL makes full-quaternion goal sampling stochastic, while a diagnostic position-only goal improves sampling; the protected Gazebo reference validates only the controllable TCP approach-axis direction and separately fails closed on path geometry.
  H2: Independently of sampling, current pre-grasp/contact geometry still produces forbidden early cup penetration under the unchanged local PlanningScene.
  H3: A mismatch in cup/table dimensions, pose, frame, TCP transform, robot collision meshes, or approach touch semantics created false collision evidence.
single_variable: A=the current position plus three-axis 0.01 rad orientation goal versus B=the identical position region with no orientation goal. Only goal-constraint expression changes; all target positions, start state, model, SRDF, solver, scene, grid, planning limits, and path acceptance checks are identical.
frozen_inputs:
  source_head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  runtime_install: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  runtime_overlay_provenance_sha256: 5e7a58e82badb4bb4f3cf061c282cbcb4c68194ca4d4612f5192b77f2e22f926
  rendered_urdf_sha256: 82ead9d1716dc43773c2ed2d3c78ee30c7f53a238ab67baa3b08aebc96e7e38d
  srdf_sha256: d3e73396a809ef1a69501612eda57bfb98f80e9dc28deee93238ab8fcca88d6d
  offsets_mm: [0, 5, 10, 15, 20, 25, 30, 35, 40]
  contact_target_m: [0.0206766838, -0.2628210212, 0.2006306106]
  tcp_orientation_xyzw: [-0.0102659913, -0.0102629866, -0.7067526865, 0.7073117563]
  start_joint_names: ['1', '2', '3', '4', '5', '6']
  start_joint_positions_rad: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4650347488]
  cup_pose_m: [0.02, -0.28, 0.165]
  cup_wall_size_m: [0.020705524, 0.002, 0.088]
  cup_bottom_radius_height_m: [0.040, 0.002]
  table_pose_m: [0.0, -0.20, 0.10]
  table_size_m: [0.50, 0.60, 0.04]
  tcp_link: so101_tcp
  planning_group: arm
  allow_precontact_fingertip_contact: false
  allowed_planning_time_s: 5.0
  planning_attempts_per_mode_per_offset: 1
required_measurements:
  - Arm active variable count/names, KDL plugin, position_only_ik, and per-offset quaternion relative rotation-vector/RPY plus protected-Gazebo approach-axis error.
  - Both A/B plan results for every frozen offset.
  - Every nonempty trajectory evaluated sample-by-sample by one independent source-faithful local PlanningScene for self/cup/table collision, contact pair/depth/position, minimum clearance, joint-limit margin, and endpoint FK.
  - First collision index/pair/depth and fail-closed classification: any contact before attachment is forbidden because MOVE_ABOVE_OBJECT and DESCEND allow no touch pair; attachment touch links do not legalize approach penetration.
  - Static parity of cup/table pose, dimensions, frame, TCP transform, gripper/jaw collision meshes, and protected Gazebo approach/touch semantics.
success_criteria: Complete nine-offset A/B grid and all required measurements under unchanged provenance, with zero forbidden calls or state writes, sufficient to decide H1/H2/H3 independently.
invalid_criteria: Missing offset/mode/path sample, provenance mismatch, prestart/runtime contamination, missing contact depths, modified protected Gazebo content, or any action/controller/ExecuteTrajectory/MuJoCo state-write call.
read_only_boundary:
  services: [/compute_ik, /compute_fk, /check_state_validity, /plan_kinematic_path]
  forbidden: [controller calls, actions, ExecuteTrajectory, gripper calls, MuJoCo runtime, pause, step, qpos write, qvel write, teleport, weld, equality, production config change]
fresh_runtime:
  ros_domain_id: 148
  ros_localhost_only: 1
  simulation_session_id: task13-exp068-contract-evidence
  tmux_session: so101-task13-exp068
decision: PENDING. This PLANNED record precedes temporary diagnostic helper construction, runtime launch, and all service requests.
```

## Experiment EXP-068 Running Transition

```yaml
experiment_id: EXP-068
status: RUNNING
transition_time: 2026-08-11T23:14:23+08:00
full_restart_provenance_verified:
  ros_domain_id: 148
  prestart_graph: EMPTY
  tmux_session: so101-task13-exp068
  process_group_id: 139571
  robot_state_publisher_pid: 139671
  move_group_pid: 139672
  runtime_prefix: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  dependency_prefix: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
  live_kinematics_solver: kdl_kinematics_plugin/KDLKinematicsPlugin
  live_position_only_ik: true
  mujoco_or_controller_runtime: NONE
temporary_diagnostic_provenance:
  runner_sha256: 2dbd6514c3cb8e28d41cdd1e22681186a641d9aa2ee56a5072cbcd44b924bd52
  launch_sha256: 2c2bec252a88f4fb6122a359580b88da86ae526260b92ac32df737a7ea161041
  helper_source_sha256: 4a43d08c7eacbb72d11106e49b9be1a605e6e7b13d952a8d30e4728593a4ea27
  helper_binary_sha256: 32ae64d6372da37ba0756674726c3808300968adf104662ae11ef614a6bb9d63
  helper_build_log_sha256: 13a83644936204ee8f8e940fa9fa7a7af0c8b397d3c562a84c21c50370f0df6f
  static_parity_sha256: 3db0624c988354da74fc42d3a37a2d3189d2cbda26ec6fe2e4e3784530e794b6
  prelaunch_isolation_sha256: 2b743f90c47cb72dba30e36eaca96e2fb39d608264fcc33d6bb93d91d865a9b8
  running_provenance_sha256: 787094da8ca292f5ae2ff07617c0145ad84a207ab208c2f6cb7ee345e7fa902b
action_state: No diagnostic service request had been sent at this transition. The runner contains only GetPositionIK, GetPositionFK, GetStateValidity, and GetMotionPlan clients and no action client.
```

## Experiment EXP-068 Terminal Result

```yaml
experiment_id: EXP-068
status: VALID
terminal_result: DIAGNOSED_H1_AND_H2_H3_DISFAVORED_NO_FIX_GATE
terminal_time: 2026-08-11T23:18:35+08:00
grid_complete: true
read_only_contract:
  action_calls: 0
  execute_trajectory_calls: 0
  controller_calls: 0
  mujoco_state_writes: 0
arm_contract:
  actual_active_dof: 5
  active_variables: ['1', '2', '3', '4', '5']
  group_tip: so101_tcp
  kinematics_solver: kdl_kinematics_plugin/KDLKinematicsPlugin
  position_only_ik: true
  protected_gazebo_orientation_semantics: Rotate TCP local [0, 0, -1] into world and require angular error from world [0, 0, -1] no greater than 0.08726646259971647 rad; full quaternion roll is not the protected reference gate.
ab_result:
  full_pose_success_count: 4 of 9; offsets [0, 10, 15, 30]
  position_only_success_count: 9 of 9
  full_fail_position_success_offsets_mm: [5, 20, 25, 35, 40]
  conclusion: Goal sampling improved from 4/9 to 9/9 when only the goal-constraint expression changed, supporting H1. Full-pose success remains stochastic across EXP-064, EXP-066, and EXP-068.
direct_ik_orientation_component_rows:
  fields: [offset_mm, relative_rotation_vector_xyz_rad, relative_rpy_xyz_rad, protected_approach_axis_error_rad]
  rows:
    - [0, [0.6530951022, -0.9655181552, -0.9151400335], [1.0745191212, -0.4125496928, -1.2765453336], 1.1483572039]
    - [5, [0.6961674988, -0.9820244573, -0.9439019855], [1.1178352127, -0.3813225012, -1.3095919187], 1.1814442883]
    - [10, [0.0009727628, -0.8075663318, -0.0028003935], [0.0028079730, -0.8075628640, -0.0041629423], 0.8366000133]
    - [15, [0.0009542308, -0.7925945508, -0.0028052102], [0.0027238061, -0.7925911913, -0.0041016485], 0.8216282259]
    - [20, [0.0009543009, -0.7780153906, -0.0028465230], [0.0026862977, -0.7780120344, -0.0041004633], 0.8070490742]
    - [25, [0.0006781898, -0.9511301610, -0.0019826503], [0.0025042318, -0.9511279945, -0.0034366448], 0.9801636100]
    - [30, [0.0006578218, -0.9403994005, -0.0019655201], [0.0024142440, -0.9403973379, -0.0033513975], 0.9694328431]
    - [35, [0.0006599338, -0.9310535790, -0.0019828722], [0.0023902098, -0.9310515210, -0.0033404447], 0.9600870244]
    - [40, [0.0007054678, -0.9229988770, -0.0020714778], [0.0024849420, -0.9229966298, -0.0034680534], 0.9520323447]
whole_path_rows:
  fields: [offset_mm, mode, plan_code, points, cup_collision_samples, first_collision_index, first_pair, first_index_max_depth_m, minimum_cup_clearance_m, minimum_table_clearance_m, minimum_joint_margin_rad, endpoint_protected_axis_error_rad]
  rows:
    - [0, full_pose, 1, 38, 8, 28, jaw/plastic_cup, 0.0011598315, -1.0, 0.0592024062, 0.5246349697, 0.0388291377]
    - [0, position_only, 1, 51, 18, 33, gripper/plastic_cup, 0.0030945870, -1.0, 0.0572994231, 0.2028327041, 1.1506338290]
    - [5, full_pose, 99999, 0, 0, null, null, null, null, null, null, null]
    - [5, position_only, 1, 51, 17, 34, gripper/plastic_cup, 0.0016193835, -1.0, 0.0618267036, 0.1697694334, 1.1786274385]
    - [10, full_pose, 1, 40, 6, 31, gripper/plastic_cup, 0.0009747141, -1.0, 0.0693218646, 0.5246349697, 0.0239313242]
    - [10, position_only, 1, 43, 13, 30, gripper/plastic_cup, 0.0007745291, -1.0, 0.0524622646, 0.5184426513, 0.8406412024]
    - [15, full_pose, 1, 40, 5, 32, gripper/plastic_cup, 0.0050365530, -1.0, 0.0748916203, 0.5246349697, 0.0342898799]
    - [15, position_only, 1, 43, 11, 32, gripper/plastic_cup, 0.0047176977, -1.0, 0.0569670592, 0.5040114167, 0.8239710305]
    - [20, full_pose, 99999, 0, 0, null, null, null, null, null, null, null]
    - [20, position_only, 1, 43, 10, 33, gripper/plastic_cup, 0.0021981563, -1.0, 0.0627378583, 0.4871167154, 0.8125042248]
    - [25, full_pose, 99999, 0, 0, null, null, null, null, null, null, null]
    - [25, position_only, 1, 43, 9, 34, gripper/plastic_cup, 0.0009867555, -1.0, 0.0673500567, 0.4737437649, 0.8024169386]
    - [30, full_pose, 1, 42, 0, null, null, null, 0.0003461158, 0.0897453801, 0.5246349697, 0.0249831169]
    - [30, position_only, 1, 44, 10, 34, gripper/plastic_cup, 0.0000942747, -1.0, 0.0714097144, 0.4312262876, 0.9703625457]
    - [35, full_pose, 99999, 0, 0, null, null, null, null, null, null, null]
    - [35, position_only, 1, 45, 9, 36, gripper/plastic_cup, 0.0001520767, -1.0, 0.0759175855, 0.4138078976, 0.9597526895]
    - [40, full_pose, 99999, 0, 0, null, null, null, null, null, null, null]
    - [40, position_only, 1, 45, 6, 39, gripper/plastic_cup, 0.0003070295, -1.0, 0.0813709928, 0.3948910818, 0.9529940936]
collision_classification:
  - Every reported collision is cup penetration before attachment. Because the protected MOVE_ABOVE_OBJECT and DESCEND states both have allowed_touch_pairs=[] and temporal_contact=null, none is an allowed final fingertip contact.
  - The first pair is jaw/plastic_cup at full-pose 0 mm and gripper/plastic_cup for all other colliding paths. Both links are forbidden during approach; post-attachment touch_links=[gripper,jaw] does not retroactively allow them.
  - All trajectories had zero self-collision samples and zero table-collision samples. All nonempty paths had positive joint-limit margin; collision paths remain rejected irrespective of margin.
  - The 30 mm full-pose sample alone had no collision, positive cup/table clearance, positive joint margin, and endpoint approach-axis error within the protected tolerance. It is not a repaired request contract and is not executable evidence because full-pose success changed across the three fresh runs.
hypothesis_decisions:
  H1: SUPPORTED. Position-only KDL plus a full-quaternion goal creates stochastic goal sampling; B improves sampling but does not satisfy the protected controllable-axis endpoint contract.
  H2: SUPPORTED. Every B trajectory intersects the cup, with first penetration at indices 30-39 and positive FCL depths. Several A trajectories independently reproduce cup penetration.
  H3: DISFAVORED. Cup/table world poses and dimensions, world frame, TCP transform, fixed-finger/moving-jaw/fixed-pad/moving-pad meshes, and Gazebo approach/touch semantics match; fresh local FCL reproduces link/cup penetration with positions, normals, and depths.
request_fix_gate:
  - No unique production MoveIt goal expression is established. The protected Gazebo reference uniquely defines an external approach-axis validator, but MoveIt's present three-axis OrientationConstraint and a goal with orientation entirely removed are not equivalent ways to sample that axis constraint.
  - B is specifically disproven as a fix because all nine endpoints violate the protected approach-axis tolerance and all nine paths collide. Simply deleting orientation checks would not fail closed.
  - No production file was changed, so RED/GREEN was not entered and EXP-067 was not preregistered or run.
evidence:
  root: /tmp/so101-debug-mujoco-task13-exp068-MQn9fJqx
  result_sha256: ce7681517fbf6c01079ad2abb76aef275b87a83b29a799a7fd93ef298f4561b0
  geometry_query_sha256: 94d7fb6b9c073092b5ce09df979985224f1b5e5068c1accf7789af576e1675c7
  geometry_results_sha256: 8c185494caa3a9cb08df191a9f591134fc69e40188887ffaa73c9acf451cbe4d
  summary_sha256: 2771f856a7316e7fd638a4fd24f9bf31a19254a8e03eee7279d648a53fbd6542
  static_parity_sha256: 3db0624c988354da74fc42d3a37a2d3189d2cbda26ec6fe2e4e3784530e794b6
  runner_log_sha256: da1396a6c6ffd2e504ba865b11e05389bcba780ab03403bc4c6e0bf7c7c3ea3e
  stack_log_sha256: 9e2c7af9e248b6bab18ab1d8a44c1f6b75de9545202b692317986bcbfbbaf1f2
  postrun_audit_sha256: 83dfdb6545aebf888f70c9913d65d1dd3a3572f570caa6f9ccd646effbf0cc31
  poststop_isolation_sha256: 5c39c4cf44478ffde183d8a0b0a09dc40a9e875af7c5025d63c63864c2e38eb4
decision: KEEP VALID as the supplemental read-only contract diagnosis. Do not modify the planning request, run EXP-067, execute motion, or begin Task 13.5.
```

## Checkpoint CP-101

```yaml
checkpoint_id: CP-101
checkpoint_time: 2026-08-11T23:18:35+08:00
last_valid_experiment: EXP-068
current_hypothesis: The next bounded geometry investigation should preserve solver, model, final contact target, and orientation while changing only the approach-path geometry to use one outside/lateral waypoint; request-expression work alone cannot remove the observed cup penetration.
working_tree_status: Task 13 dirty files remain uncommitted and preserved. HEAD and origin/codex/so101-mujoco-ros2 remain 1548acb20a2bd376e1bbe867603d824d26ddfb21. Protected Gazebo tracked diff/status remain empty.
owned_processes: NONE. The EXP-068 tmux session/process group was stopped and domain 148 is empty.
preserved_processes: Existing codex tmux session remains; no unrelated process or session was changed.
confirmed_conclusions:
  - EXP-068 separates goal sampling from geometry. Position-only goals improve service success to 9/9 but every resulting path penetrates the cup and every endpoint violates the protected controllable approach-axis gate.
  - H3 remains disfavored by exact source parity, including all 28 relevant fixed/moving finger and pad collision meshes plus protected Gazebo touch semantics.
  - One full-pose 30 mm plan is safe in this stochastic sample, but it does not define a deterministic request repair and was not executed.
  - No unique fail-closed production request expression was derived, so no TDD repair and no EXP-067 occurred.
next_single_variable_geometry_proposal:
  status: PROPOSED_NOT_PLANNED_NOT_AUTHORIZED
  variable: approach_path_geometry
  old_value: Direct plan from frozen q1-q6 start to a frozen vertical-grid pose at the contact x/y.
  proposed_value: Add exactly one outside/lateral approach waypoint at the protected Gazebo MOVE_ABOVE_OBJECT TCP reference [0.020673889, -0.254030551, 0.259837209], then retain the unchanged final contact target [0.0206766838, -0.2628210212, 0.2006306106].
  frozen_unchanged: [source, install, model, SRDF, KDL position-only solver, start q1-q6, cup/table scene, TCP link, final contact target, final target quaternion, contact thresholds, allow_precontact_fingertip_contact=false]
  required_future_gate: A separately authorized PLANNED read-only experiment must validate both segments with the same local PlanningScene and protected approach-axis validator before any motion qualification.
test_contamination: The 15 known baseline package/isolation failures remain disclosed and were not bypassed; no protected ignored file was deleted or rewritten. Fresh post-experiment verification is pending at this checkpoint.
evidence:
  root: /tmp/so101-debug-mujoco-task13-exp068-MQn9fJqx
  result_sha256: ce7681517fbf6c01079ad2abb76aef275b87a83b29a799a7fd93ef298f4561b0
  summary_sha256: 2771f856a7316e7fd638a4fd24f9bf31a19254a8e03eee7279d648a53fbd6542
  poststop_isolation_sha256: 5c39c4cf44478ffde183d8a0b0a09dc40a9e875af7c5025d63c63864c2e38eb4
next_experiment: NONE
next_command: Run fresh ledger and boundary verification, record it monotonically, then stop and report. Do not preregister or execute the proposed geometry experiment without new authorization.
```

## Checkpoint CP-102

```yaml
checkpoint_id: CP-102
checkpoint_time: 2026-08-11T23:22:48+08:00
last_valid_experiment: EXP-068
current_hypothesis: Unchanged direct approach geometry and position-only goal sampling are both unsafe; the next admissible investigation is the single outside/lateral waypoint proposal recorded in CP-101, but it is not authorized or PLANNED.
verification_correction:
  - The first fresh ledger check found that the temporary header value TASK_13_EXP068_VALID_VERIFICATION_PENDING violated the existing ledger_commit_pending=true naming contract, adding one new test failure to the known 15.
  - Only the header status label was corrected to TASK_13_CONTRACT_DIAGNOSTIC_STOP_PENDING_COMMIT. The fresh rerun passed the ledger contract and restored the repository-isolation result to exactly the 15 pre-existing failures.
verification_state:
  ledger_contract: PASS; 1 passed, 33 deselected.
  repository_isolation: EXPECTED CONTAMINATED RESULT; 19 passed, 15 failed. The failures are the same protected ignored-manifest mismatch and committed visual_reference_updates provenance incompatibility already disclosed before EXP-068.
  ruff: PASS; all checks passed and 79 files already formatted.
  migration_isolation: EXPECTED BASELINE FAIL; protected nontracked actual aaa2030e5a56b6a8ec959a24c1c42dc5afdc5d566e2ccb6eaadd704c0b7b44f6 differs from recorded 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
  result_contract: PASS; nine offsets, 18 A/B records, arm five-DoF metadata, orientation components, all nonempty path samples, per-contact depth/position/normal, and 28 mesh parity pairs were checked from the saved JSON.
  final_boundaries: PASS; git diff check, unchanged local/remote HEAD, exact dirty set, protected Gazebo tracked diff/status, protected draft hashes, false approval/enable/precontact gates, empty domain 148, no task runtime, and codex-only tmux state.
evidence:
  root: /tmp/so101-debug-mujoco-task13-exp068-MQn9fJqx
  final_ledger_pytest_sha256: 2778392902065c53a85331e4a8033096dc7d2a046de476a5af3ddc6a27d0e5ca
  final_repository_isolation_pytest_sha256: a014802a6f430b16cf1d2c349856d460c90af753f8376714a568fb597658d710
  final_ruff_sha256: e3e75536809fddead684100d219413a6157dcc009e3a2f510ac2e0f3d1e2307a
  final_migration_isolation_sha256: 0687d85ecf399fd28dfa52094daac4945a680ae9266bbe571987e765d7f5b025
  final_boundary_audit_sha256: 05ff671d221db45c6c910c0a6b105aacfc79923f7f9fc0c67b883f68ac726652
working_tree_status: HEAD and origin/codex/so101-mujoco-ros2 remain 1548acb20a2bd376e1bbe867603d824d26ddfb21. Task 13 dirty work is preserved; protected Gazebo tracked status is empty. No commit or push occurred.
owned_processes: NONE. Domain 148 remains empty and the only tmux session is the pre-existing codex session.
next_experiment: NONE
next_command: Mandatory bounded diagnostic stop. Do not implement request or geometry changes, run EXP-067, execute motion, start Task 13.5, approve/enable thresholds, commit/push, start clean-shutdown work, or begin Task 14/15 without new authorization.
```

## Checkpoint CP-103

```yaml
checkpoint_id: CP-103
checkpoint_time: 2026-08-11T23:30:00+08:00
recovery_reason: The user explicitly requested direct takeover, then narrowed the immediate request to opening RViz and MuJoCo Viewer side by side and running a visible planning task.
last_valid_experiment: EXP-068
working_tree_status: Preserve the exact Task 13 dirty path set and protected draft hashes recorded by CP-102. HEAD and origin/codex/so101-mujoco-ros2 remain 1548acb20a2bd376e1bbe867603d824d26ddfb21.
owned_processes: NONE before launch. The previous ai-station Codex process exited to its tmux zsh prompt; no MoveIt, MuJoCo, ros2_control, RViz, or task runtime was active.
preserved_processes: The pre-existing codex tmux shell is preserved and will not own the GUI stack.
authorization_boundary:
  - Start a new owned GUI simulation stack with MuJoCo Viewer and RViz.
  - Run plan-only service requests and publish one resulting trajectory to /display_planned_path for visual inspection.
  - Do not call ExecuteTrajectory, controller actions, gripper actions, or mutate MuJoCo state as part of EXP-069.
  - The known missing authoritative cup/table Planning Scene means EXP-069 is visualization evidence only and cannot authorize motion execution.
next_experiment: EXP-069
next_command: Start the owned GUI stack on empty ROS domain 149, tile RViz left and MuJoCo Viewer right, then publish one bounded full-pose plan for visual inspection.
```

## Experiment EXP-069

```yaml
experiment_id: EXP-069
prior_experiment: EXP-068 VALID; CP-103 direct-takeover authorization
status: PLANNED
lifecycle: FULL_RESTART
run_mode: plan_only_visualization
hypothesis: The current MuJoCo/ros2_control/MoveIt stack can produce a nonempty full-pose plan from the live initial joint state and RViz can display it while MuJoCo Viewer remains open and physics is not commanded by the planner.
single_variable: GUI-visible planning and /display_planned_path publication at the frozen 30 mm pre-grasp target; no production source, solver, geometry, target, controller, dynamics, or contact-threshold change.
frozen_inputs:
  source_head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  dependency_gitlink_and_checkout: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
  ros_domain_id: 149
  simulation_session_id: so101-exp069-gui-plan
  planning_group: arm
  tcp_link: so101_tcp
  target_position_m: [0.0206766838, -0.2628210212, 0.2306306106]
  target_orientation_xyzw: [-0.0102659913, -0.0102629866, -0.7067526865, 0.7073117563]
  position_tolerance_m: 0.0005
  orientation_tolerance_rad: [0.01, 0.01, 0.01]
  maximum_planning_attempts: 12
  execute_trajectory: false
read_only_boundary:
  allowed: [/plan_kinematic_path, /display_planned_path publication, joint-state and process readback, GUI camera/layout]
  forbidden: [ExecuteTrajectory, controller action, gripper action, pause, step, qpos write, qvel write, teleport, weld, equality, production config change]
success_criteria:
  - MuJoCo Viewer and RViz are both visible and verified in a fresh desktop capture.
  - The two windows are tiled left/right and their outer geometry is read back within 12 px of the current EWMH work area split.
  - At least one bounded full-pose request returns success with a nonempty trajectory and that exact RobotTrajectory is published to /display_planned_path.
  - RViz visibly displays the planned path; no execution/action/state-write call occurs.
failure_criteria: Terminalize VALID/FAIL if the bounded attempts produce no nonempty plan or the GUI/path cannot be visually verified; do not execute or relax constraints.
invalid_criteria: Runtime/provenance mismatch, duplicate stack, missing start-state readback, GUI ambiguity, any forbidden call, or modification of protected Gazebo content.
evidence_root: /tmp/so101-debug-mujoco-task13-exp069-gui-plan
decision: PENDING. This entry precedes GUI/runtime launch and all planning requests.
```

## Experiment EXP-069 Terminal Result

```yaml
experiment_id: EXP-069
status: VALID
terminal_result: VISUALIZATION_ONLY_DIRECT_TCP_ROUTE_REJECTED
terminal_time: 2026-08-11T23:47:21+08:00
result:
  selected_attempt: 10
  selected_trajectory_points: 42
  display_topic: /display_planned_path
  execute_trajectory_calls: 0
  controller_action_calls: 0
  gui_layout: RViz left and MuJoCo Viewer right
limitation:
  - The Planning Scene did not yet include the authoritative table, cup, and pedestal when this request was planned.
  - The request planned directly to one TCP pose and did not reproduce the Gazebo preopen, MOVE_ABOVE_OBJECT, and DESCEND lifecycle.
  - Therefore this result is retained only as GUI plumbing evidence and cannot authorize execution.
evidence:
  result: /tmp/so101-debug-mujoco-task13-exp069-gui-plan/plan-display.json
  result_sha256: 52553f9098ba7bdc6f4425b403d14e3e2502c1ab90190e0c597edac8d880dc8a
decision: KEEP VALID as visualization-only evidence; reject the direct-TCP experimental route.
```

## Checkpoint CP-104

```yaml
checkpoint_id: CP-104
checkpoint_time: 2026-08-11T23:50:00+08:00
last_valid_experiment: EXP-069
user_correction:
  - The Gazebo demo preopens the gripper and approaches in phases.
  - A direct TCP move to the pre-Close pose is not a representative or safe experiment.
required_experiment_lifecycle: [PREOPEN_GRIPPER, MOVE_ABOVE_OBJECT, DESCEND, STOP_BEFORE_CLOSE]
required_scene: Formal MoveIt Planning Scene containing exact table, plastic_cup, and pedestal geometry and colors before workflow startup.
execution_boundary: Plan-only first. Any later execution must keep MuJoCo physics running and stop before Close if early contact, cup movement, stale evidence, reset, or instability is observed.
next_experiment: EXP-070
```

## Experiment EXP-070

```yaml
experiment_id: EXP-070
status: VALID
run_mode: temporary_read_only_staged_plan_diagnostic
terminal_time: 2026-08-11T23:54:16+08:00
single_variable: Replace the rejected direct-TCP request with the frozen Gazebo waypoint ladders while preserving the existing GUI stack and performing no execution.
result:
  preopen_q6_rad: 0.465038
  move_above_object_segments: 10
  descend_segments: 5
  selected_segments: 15
  planning_scene_world_objects: [pedestal, plastic_cup, table]
  execute_trajectory_calls: 0
  controller_action_calls: 0
  close_gripper_calls: 0
  status: PLAN_ONLY_VALID
limitation: The helper was temporary diagnostic code. Production acceptance requires the same contract through an installed so101_mujoco_demo_py executable with an explicit execute gate, live start-state handoff checks, safety monitoring, and atomic evidence.
evidence:
  result: /tmp/so101-debug-mujoco-task13-exp070-staged-plan/result.json
  result_sha256: cd90ef89f40d1399efa3d9d58703f066ab325ff6271b7981b29fad730110b951
decision: KEEP VALID as staged-plan diagnostic evidence only.
```

## Checkpoint CP-105

```yaml
checkpoint_id: CP-105
checkpoint_time: 2026-08-12T00:18:00+08:00
last_valid_experiment: EXP-070
implementation:
  - Added a formal scene_setup executable and launch gate; the workflow cannot start until the exact task Planning Scene is applied and read back.
  - Added staged_approach as an installed package executable with explicit plan_only versus dual-gated execute modes.
  - The full q1-q6 current state, including preopened q6, is sent as the MoveIt start state while only q1-q5 are goal constrained.
  - Execution is fail closed on stale MuJoCo evidence, pause, reset/session change, early fingertip contact, forbidden cup contact, cup displacement, force boundary, start drift, convergence failure, or an unstable joint window.
  - No Close command exists in the staged-approach experiment and no contact-calibration draft was approved or enabled.
verification:
  ruff: PASS
  focused_tests: 40 passed, 1 skipped
  isolated_colcon_build: PASS; one package built
  installed_executables: [headless_execution, scene_setup, staged_approach]
protected_gazebo_tree: No tracked diff or worktree status.
next_experiment: EXP-071
```

## Checkpoint CP-106

```yaml
checkpoint_id: CP-106
checkpoint_time: 2026-08-12T00:25:00+08:00
last_valid_experiment: EXP-070
current_hypothesis: The installed formal staged_approach executable can plan all 15 frozen approach segments from the live initial state while verifying the authoritative Planning Scene and issuing no action or physics command.
owned_runtime:
  ros_domain_id: 149
  simulation_session_id: so101-exp069-gui-plan
  tmux_session: so101-mujoco-gui
  gui: MuJoCo Viewer and RViz remain open side by side.
authorization_boundary: The user authorized continued planning experiments and later staged execution, but EXP-071 itself is plan-only.
next_experiment: EXP-071
```

## Experiment EXP-071

```yaml
experiment_id: EXP-071
prior_experiment: EXP-070 VALID; CP-105 formal implementation gate passed
status: PLANNED
lifecycle: REUSE_OWNED_GUI_STACK_READ_ONLY
run_mode: formal_staged_plan_only
hypothesis: The installed staged_approach executable will verify the formal scene and plan PREOPEN display plus all 10 MOVE_ABOVE_OBJECT and 5 DESCEND segments without executing motion.
frozen_inputs:
  source_head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  dependency_checkout: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
  ros_domain_id: 149
  simulation_session_id: so101-exp069-gui-plan
  staged_approach_source_sha256: 06e3b30ba0830e058eff42bd06010f842e57a9155729e148520bf414e4367a18
  policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
  preopen_q6_rad: 0.465038
  phases: [MOVE_ABOVE_OBJECT, DESCEND]
  execute: false
success_criteria:
  - Planning Scene exact geometry and colors are read back before planning.
  - Exactly 15 segments are selected with trajectory endpoints within the fixed convergence tolerance.
  - The cumulative DisplayTrajectory is published for RViz inspection.
  - physics_paused_calls, Close calls, ExecuteTrajectory calls, and controller action calls remain zero.
failure_criteria: Any missing scene geometry, planning failure after bounded retries, endpoint mismatch, runtime provenance mismatch, or forbidden action fails the experiment without relaxing a threshold.
evidence_root: /tmp/so101-debug-mujoco-task13-exp071-formal-staged-plan
decision: PENDING. This record precedes the formal package executable invocation.
```

## Experiment EXP-071 Terminal Result

```yaml
experiment_id: EXP-071
status: VALID
terminal_result: FORMAL_STAGED_PLAN_CLOSE_READY
terminal_time: 2026-08-12T00:26:26+08:00
result:
  installed_executable: so101_mujoco_demo_py/staged_approach
  planning_scene_verified: true
  mode: plan_only
  selected_segments: 15
  attempts_per_segment: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
  maximum_trajectory_endpoint_error_rad: 0.00009933590530414316
  final_open_joint_positions_rad: [-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465, 0.465038]
  physics_paused_calls: 0
  close_gripper_calls: 0
  execute_trajectory_calls: 0
evidence:
  result: /tmp/so101-debug-mujoco-task13-exp071-formal-staged-plan/result.json
  result_sha256: 9157d4726dd319eb6a4101581941e6db357664a6b2ca78c5ebcbd3d3958ac436
decision: KEEP VALID. This authorizes only a separately preregistered staged execution from the unchanged live initial state.
```

## Checkpoint CP-107

```yaml
checkpoint_id: CP-107
checkpoint_time: 2026-08-12T00:27:00+08:00
last_valid_experiment: EXP-071
pre_execution_readback:
  joint_names: ['1', '2', '3', '4', '5', '6']
  positions_rad: [-0.000000003636221687, 0.001079804375380911, 0.0009069895288303677, 0.00023452701017389544, 0.000000307070333499, -0.000005825630929604]
  velocities_rad_s: approximately zero for all six joints
  conclusion: The plan-only run did not move the robot and the owned MuJoCo stack remains at its initial state.
execution_design:
  - Command q6 to the frozen preopen target and verify convergence.
  - For each of 15 frozen policy waypoints, require a 0.20 second unpaused stable window, plan from the fresh full q1-q6 state, reject plan-to-execute drift above 0.01 rad, execute, and verify convergence.
  - Continuously cancel and fail on stale evidence, pause/reset/session change, early fingertip contact, forbidden cup contact, cup displacement above 3 mm, or force above 11.60 N.
  - Stop after DESCEND with q6 still preopened. Do not command Close.
next_experiment: EXP-072
```

## Experiment EXP-072

```yaml
experiment_id: EXP-072
prior_experiment: EXP-071 VALID; CP-107 stable initial-state readback
status: PLANNED
lifecycle: REUSE_OWNED_GUI_STACK_EXECUTE
run_mode: formal_staged_execute_stop_before_close
hypothesis: With unpaused physics and q6 preopened, all 15 frozen approach segments can be planned from fresh stable state and executed through MoveIt without pre-Close contact or cup displacement.
frozen_inputs:
  source_head: 1548acb20a2bd376e1bbe867603d824d26ddfb21
  dependency_checkout: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
  ros_domain_id: 149
  simulation_session_id: so101-exp069-gui-plan
  staged_approach_source_sha256: 06e3b30ba0830e058eff42bd06010f842e57a9155729e148520bf414e4367a18
  policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
  preopen_q6_rad: 0.465038
  phases: [MOVE_ABOVE_OBJECT, DESCEND]
  physics_pause_allowed: false
  close_allowed: false
  maximum_replans_per_segment: 2
  plan_start_tolerance_rad: 0.01
  convergence_tolerance_rad: 0.01
safety_boundaries:
  maximum_preclose_cup_displacement_m: 0.003
  maximum_preclose_force_n: 11.60
  maximum_evidence_age_s: 0.50
  early_fingertip_contact_allowed: false
  non_table_cup_contact_allowed: false
success_criteria:
  - Preopen converges and every segment executes with bounded planning and fresh state/evidence.
  - Actual final q1-q5 is within 0.01 rad of the final DESCEND waypoint and q6 remains within 0.01 rad of preopen.
  - MuJoCo evidence advances while unpaused, reset/session provenance remains unchanged, and the cup moves no more than 3 mm before Close.
  - The result is CLOSE_READY and close_gripper_calls remains zero.
failure_criteria: Fail closed and cancel the owned trajectory on any boundary violation; do not relax thresholds or proceed to Close.
evidence_root: /tmp/so101-debug-mujoco-task13-exp072-formal-staged-execute
decision: PENDING. This entry precedes the first gripper/controller/ExecuteTrajectory action of EXP-072.
```

## Experiment EXP-072 Terminal Result

```yaml
experiment_id: EXP-072
status: VALID
terminal_result: PHYSICAL_CLOSE_READY_WITH_UNPAUSED_STAGED_EXECUTION
terminal_time: 2026-08-12T00:28:30+08:00
result:
  status: CLOSE_READY
  preopen_actual_q6_rad: 0.46374169771140566
  selected_segments: 15
  maximum_attempts_per_segment: 1
  maximum_plan_to_execute_drift_rad: 0.000018661116396367916
  maximum_actual_endpoint_error_rad: 0.0005860968467436001
  final_joint_positions_rad: [-0.00016372898158321418, 0.4726993433667315, 0.21490240185264656, 0.854993211832095, 0.0005211211883640602, 0.46503647008102744]
  cup_displacement_m: 0.0000000619551001829137
  initial_simulation_step: 262970
  final_simulation_step: 265140
  reset_epoch: 0
  paused: false
  fingertip_contact_count: 0
  close_gripper_calls: 0
visual_evidence:
  method: cua-driver desktop capture
  screenshot: /tmp/so101-debug-mujoco-task13-exp072-formal-staged-execute/close-ready-cua.png
  screenshot_sha256: 86654679ea3654c5c635cf0c6bb39fa7348f85790694dd9728d56916968f2c2f
  dimensions: [5120, 2880]
  observation: RViz left shows the formal scene and cumulative planned path; MuJoCo right shows the open gripper inserted at the cup wall, ready for Close.
evidence:
  result: /tmp/so101-debug-mujoco-task13-exp072-formal-staged-execute/result.json
  result_sha256: 90d9fc5661ace70f755db28461fec400a179636c276a84b6ac2ff7b562c5e085
decision: KEEP VALID as the unpaused staged approach execution. It does not yet prove a physical grasp or pick/place.
```

## Checkpoint CP-108

```yaml
checkpoint_id: CP-108
checkpoint_time: 2026-08-12T00:38:00+08:00
last_valid_experiment: EXP-072
current_hypothesis: The frozen grasp_close_q6 can create bilateral fingertip contact at the verified Close-ready pose, after which one bounded LIFT waypoint can demonstrate that the cup follows the gripper without a simulator constraint.
planning_scene_boundary:
  - After physical bilateral contact is observed, plastic_cup may be moved from the MoveIt world to an AttachedCollisionObject on link gripper with touch_links [gripper, jaw].
  - This attachment is a collision-planning shadow only. It must not create any MuJoCo weld, equality, mocap, teleport, qpos, or qvel change.
  - Physical success is determined only from atomic MuJoCo contact and object-state evidence.
next_experiment: EXP-073
```

## Experiment EXP-073

```yaml
experiment_id: EXP-073
prior_experiment: EXP-072 VALID close-ready state
status: PLANNED
lifecycle: CONTINUE_OWNED_GUI_STACK_PHYSICAL_GRASP_PROBE
run_mode: close_attach_shadow_and_first_lift_waypoint
hypothesis: Closing q6 to the frozen grasp target creates sustained bilateral fingertip contact, and executing only LIFT waypoint 0 raises the physical cup while contact remains bilateral.
frozen_inputs:
  ros_domain_id: 149
  simulation_session_id: so101-exp069-gui-plan
  close_target_q6_rad: -0.047608632840292
  lift_waypoint_0_rad: [-0.000284124852, 0.381814591288, 0.272246878070, 0.916741182602, -0.000291565154]
  maximum_force_n: 11.60
  minimum_bilateral_duration_s: 0.20
  maximum_plan_to_execute_drift_rad: 0.01
  convergence_tolerance_rad: 0.01
forbidden_simulator_mechanisms: [weld, equality, adhesion, mocap, teleport, qpos_write, qvel_write, pause]
success_criteria:
  - The Close action produces left and right fingertip contact for at least 0.20 s without exceeding 11.60 N or changing session/reset provenance.
  - MoveIt reports plastic_cup attached to gripper and absent from the world only after physical bilateral contact exists.
  - LIFT waypoint 0 executes with bounded drift; cup z increases by at least 5 mm and bilateral contact remains at the endpoint.
  - MuJoCo evidence advances unpaused and no simulator constraint or direct object-state write is invoked.
failure_criteria: On missing bilateral contact, unsafe force, action failure, scene-shadow failure, planning/execution failure, slip, stale evidence, pause, or reset, stop before further transfer; do not relax thresholds.
evidence_root: /tmp/so101-debug-mujoco-task13-exp073-grasp-probe
decision: PENDING. This entry precedes Close, MoveIt shadow attachment, and LIFT execution.
```

## Experiment EXP-073 Terminal Result

```yaml
experiment_id: EXP-073
status: VALID
terminal_result: PHYSICAL_GRASP_FAILURE_MISSING_SEATING_PRELOAD
terminal_time: 2026-08-12T00:43:00+08:00
actions_completed: [CLOSE, ATTACH_MOVEIT_COLLISION_SHADOW, LIFT_WAYPOINT_0]
result:
  close_action: SUCCEEDED
  close_q6_rad: -0.04760629894348962
  sustained_bilateral_samples: 19
  moveit_attached_ids: [plastic_cup]
  moveit_world_ids_after_attach: [pedestal, table]
  lift_trajectory_points: 10
  plan_to_execute_drift_rad: 0.00000018263232395843154
  transient_cup_z_increase_m: 0.0018271075044508367
  settled_cup_position_world_m: [0.020002714629709904, -0.26857298362480636, 0.16490533020352235]
  settled_table_contact: true
  settled_left_contact_forces_n: [0.012298655729818003, 0.012298682879844182, 0.0091612575629419]
  settled_right_contact_forces_n: [0.033690325149744266]
diagnosis:
  - The cup did not remain lifted; it returned to table support and was pushed approximately 10 mm laterally.
  - Bilateral contact existed but total grip force was insufficient to overcome the approximately 0.196 N cup weight.
  - The protected Gazebo chain applies seating_preload_rad=0.006 after nominal Close and holds that preload through MICRO_LIFT. EXP-073 omitted this required lifecycle step.
  - No evidence supports changing friction, adding a simulator constraint, or relaxing the physical outcome contract.
evidence:
  result: /tmp/so101-debug-mujoco-task13-exp073-grasp-probe/result.json
  result_sha256: e3b91141eb977677b85c33503892b14e9460e90f3734aa6054a0c283826b7d14
decision: KEEP VALID as a physical failure. Do not continue transfer from this displaced-cup state.
```

## Checkpoint CP-109

```yaml
checkpoint_id: CP-109
checkpoint_time: 2026-08-12T00:45:00+08:00
last_valid_experiment: EXP-073
recovery_requirement:
  - Reset the owned MuJoCo stack to keyframe task_start and verify reset_epoch increments, simulation step restarts, q1-q6 return to the initial state, and the cup returns to its source pose.
  - Reapply and read back the complete formal Planning Scene so the stale MoveIt attachment is removed and table, pedestal, and plastic_cup return to the world.
  - Reexecute the already-qualified preopen plus 15-stage approach with unpaused physics, stopping before Close.
next_experiment: EXP-074
```

## Experiment EXP-074

```yaml
experiment_id: EXP-074
prior_experiment: EXP-073 VALID failure requiring reset
status: PLANNED
lifecycle: RESET_WORLD
run_mode: reset_scene_rebuild_and_formal_reapproach
hypothesis: The qualified reset, formal scene setup, and staged approach can restore the owned GUI stack to the same Close-ready state with a new reset epoch and the cup at the original source pose.
frozen_inputs:
  ros_domain_id: 149
  simulation_session_id: so101-exp069-gui-plan
  reset_keyframe: task_start
  approach_executable: so101_mujoco_demo_py/staged_approach
  phases: [MOVE_ABOVE_OBJECT, DESCEND]
  preopen_q6_rad: 0.465038
success_criteria:
  - ResetWorld returns success; reset_epoch increments and evidence restarts from the reset boundary without changing simulation_session_id.
  - q1-q6 and cup pose match task_start within existing reset tolerances.
  - scene_setup readback contains table, pedestal, plastic_cup with exact primitive counts and colors and no attached object.
  - The formal staged approach again reaches CLOSE_READY with no pre-Close contact, cup displacement, pause, or reset during motion.
failure_criteria: Any reset, scene readback, staged plan/execution, provenance, or safety failure stops before Close.
evidence_root: /tmp/so101-debug-mujoco-task13-exp074-reset-reapproach
decision: PENDING. This entry precedes ResetWorld and all recovery motion.
```

## Experiment EXP-074 Terminal Result

```yaml
experiment_id: EXP-074
status: INVALID
terminal_result: UNSAFE_DIRECT_RESET_FALSE_POSITIVE
terminal_time: 2026-08-12T00:50:00+08:00
observed_sequence:
  - Direct ResetWorld(task_start) was called while the simulation was running and command controllers were active.
  - The service returned success=true, but both /joint_states and /so101/simulation/evidence stopped producing fresh samples for more than 27 seconds.
  - ros2_control_node, robot_state_publisher, move_group, and RViz remained alive; the server log contained only the reset request and success message.
  - A full owned-stack restart restored telemetry, after which the qualified staged approach reached Close-ready again without executing Close.
invalid_reason:
  - The preregistered lifecycle required an effective ResetWorld transaction on the same stack. A success response without post-reset telemetry is not reset authority.
  - The full-restart fallback changed the lifecycle and therefore cannot make EXP-074 valid.
decision: KEEP INVALID. Freeze all further grasp motion until ResetWorld is fail-closed and repeatedly qualified.
```

## Checkpoint CP-110

```yaml
checkpoint_id: CP-110
checkpoint_time: 2026-08-12T01:05:00+08:00
last_valid_experiment: EXP-075
root_cause:
  - The fork ResetWorld callback accepted state replacement while MuJoCo was running and command controllers could still own stale command state.
  - Its success response validated only completion of the callback; it did not prove that the physics, controller, evidence, or Viewer loops remained usable.
implemented_boundary:
  - ResetWorld now rejects unavailable simulation state and rejects every request while sim_->run is true without mutating qpos, qvel, or simulation time.
  - The supported path remains running strict deactivate -> pause -> ResetWorld -> bounded resume -> strict activate -> fresh joint feedback -> re-pause -> atomic evidence verification.
fork_release:
  commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  tag: so101-0.0.3-r3
  origin: git@gitee.com:zjumty/mujoco_ros2_control.git
next_experiment: EXP-076
```

## Experiment EXP-075

```yaml
experiment_id: EXP-075
prior_experiment: EXP-074 INVALID
status: VALID
lifecycle: RESET_WORLD_FAIL_CLOSED_AND_REPEATED_QUALIFICATION
run_mode: fork_component_tests_headless_live_contract_and_gui_visual_reset
controlled_variables:
  model: so101_task_scene
  keyframe: task_start
  expected_joints_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  joint_tolerance_rad: 0.002
  object_tolerance_m: 0.003
  controller_names: [arm_controller, gripper_controller]
acceptance_criteria:
  - An unpaused direct ResetWorld request returns success=false, changes no reset epoch, and fresh joint feedback continues.
  - Two consecutive formal transactions each increment reset_epoch exactly once and end with paused step-zero evidence, active controllers, converged fresh joints, and the cup at task_start.
  - An invalid keyframe changes no epoch and leaves the world paused.
  - On the GUI stack, a visibly displaced Close-ready robot, gripper, and cup state is restored to task_start and confirmed through real CUA screenshots.
result:
  fork_tests: 118 passed, 0 errors, 0 failures, 0 skipped
  headless_live_contract: passed
  gui_live_contract: passed
  gui_epochs: [[0, 1], [1, 2]]
  final_reset_epoch: 2
  final_simulation_step: 0
  final_paused: true
  final_joint_positions_rad: [0.000000004184, 0.000267318810, 0.000236410832, 0.000025308964, 0.000000015461, -0.000000356937]
  final_cup_position_m: [0.019999997286, -0.279999998932, 0.164963108567]
visual_evidence:
  before_reset:
    path: /tmp/so101-reset-visual/before-reset-cua.png
    sha256: aac5feb0d67511f42421d9c54b91276b99e26e70c1f8f0499c18937f819a80eb
    observation: MuJoCo shows the open gripper descended into the cup at Close-ready; RViz shows the same displaced arm and the formal scene.
  after_reset:
    path: /tmp/so101-reset-visual/after-reset-cua.png
    sha256: 99f8ee239b539fa79c8052c3eb11a5d8d6fe610edf4744aa35d4e1ec0164bdc3
    observation: MuJoCo shows PAUSE and Status Paused; the open gripper and arm are restored to the horizontal task_start pose and the cup is restored on the table. RViz shows the matching joint state.
decision: KEEP VALID. ResetWorld is qualified for repeated use only through the formal transaction; resume Task 13 from a fresh re-approach, not from the reset pose.
```

## Experiment EXP-076

```yaml
experiment_id: EXP-076
prior_experiment: EXP-075 VALID reset qualification
status: PLANNED
lifecycle: FORMAL_SCENE_REBUILD_AND_REAPPROACH
run_mode: resume_rebuild_scene_and_stop_at_close_ready
hypothesis: After the qualified paused reset, formal scene readback and the already-qualified unpaused staged approach restore the same Close-ready state without object displacement or pre-Close contact.
success_criteria:
  - Reapply exact table, pedestal, and plastic_cup Planning Scene geometry and colors with no attached object.
  - Resume physics and execute preopen plus all MOVE_ABOVE_OBJECT and DESCEND waypoints under unchanged drift, endpoint, contact, and cup-displacement gates.
  - Stop at CLOSE_READY before applying seating preload or Close.
decision: PENDING. This entry precedes scene rebuild, resume, and all motion.
```

## Experiment EXP-076 Terminal Result

```yaml
experiment_id: EXP-076
status: VALID
terminal_result: STANDARD_FORK_STACK_RESTORED_TO_CLOSE_READY
terminal_time: 2026-08-12T01:11:22+08:00
runtime_provenance:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  dependency_tag: so101-0.0.3-r3
  install_overlay: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  staged_policy_install: /tmp/so101-staged-20260812/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-standard
result:
  planning_scene_verified: true
  planning_scene_primitive_counts: {pedestal: 1, plastic_cup: 13, table: 1}
  planning_scene_colors: [pedestal, plastic_cup, table]
  completed_phase: DESCEND
  selected_segments: 15
  maximum_attempts_per_segment: 1
  maximum_plan_to_execute_drift_rad: 0.000016366700450465288
  maximum_actual_endpoint_error_rad: 0.0005684239981664993
  preopen_actual_q6_rad: 0.46420674140947643
  final_joint_positions_rad: [-0.00012018532261347332, 0.47265601131598245, 0.21495064100102518, 0.8550053840895228, 0.0006591480255024682, 0.46503647069237125]
  initial_cup_position_world_m: [0.019999721495824203, -0.28000005119151405, 0.16490532861155277]
  final_cup_position_world_m: [0.019999668520029306, -0.2800000804822789, 0.16490533079389766]
  final_reset_epoch: 0
  final_simulation_step: 4570
  final_fingertip_contact_count: 0
  physics_paused_calls: 0
  close_gripper_calls: 0
evidence:
  result: /tmp/so101-task13-standard/exp076-reapproach.json
  result_sha256: ac15f96c450f844610efbaf3a8de0c5613d0f1fb94ae2bbd5d92f59221c41c8f
  policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
decision: KEEP VALID. This proves only the formal unpaused approach and authorizes the separately preregistered no-arm-motion seating-preload probe.
```

## Checkpoint CP-111

```yaml
checkpoint_id: CP-111
checkpoint_time: 2026-08-12T01:22:32+08:00
last_valid_experiment: EXP-076
current_hypothesis: The 0.006 rad seating preload omitted by EXP-073 is the first missing physical-grasp boundary; it must be isolated before any lift motion.
working_tree_status: HEAD and origin/codex/so101-mujoco-ros2 are eabe88885bf802fb14968547634fd06c26c1b38a. The current Task 13/14 implementation paths and execution-plan document remain intentionally dirty; protected src/so101_gazebo_demo_py tracked status is empty.
owned_processes: tmux so101-mujoco-gui owns the MuJoCo/ros2_control stack in window sim and MoveIt/RViz in window moveit; ROS_DOMAIN_ID=149; simulation_session_id=so101-task13-standard.
preserved_processes: The pre-existing attached tmux session codex is idle at its shell after its earlier Codex run and is not used for motion execution.
confirmed_conclusions:
  - EXP-075 qualifies ResetWorld only through the formal deactivate-pause-reset-resume-activate-feedback transaction.
  - EXP-076 restores table, pedestal, plastic_cup, and the open gripper to the physical CLOSE_READY state with unpaused physics.
  - Current readback at publisher_sequence 53762 has reset_epoch 0, q1-q6 approximately [-0.000119, 0.472682, 0.214917, 0.854974, 0.000662, 0.465036], the cup at [0.019999, -0.280001, 0.164905], no fingertip contact, and only table support.
disproven_routes:
  - EXP-073 proves nominal Close followed directly by the larger lift target is insufficient; the cup returned to the table and moved laterally.
open_risks:
  - The diagnostic 11.60 N force abort remains a safety boundary rather than an approved production contact threshold.
  - No physical micro-lift, transport, release, or final placement has passed yet.
next_command: Execute only /tmp/so101_exp077_seating_preload.py after its exact hash, current CLOSE_READY preconditions, runtime provenance, and EXP-077 PLANNED record are verified.
```

## Experiment EXP-077

```yaml
experiment_id: EXP-077
prior_experiment: EXP-073 VALID physical failure; EXP-076 VALID restored CLOSE_READY state
status: RUNNING
lifecycle: CONTINUE_OWNED_GUI_STACK_SEATING_PRELOAD_ONLY
run_mode: nominal_close_then_seating_preload_no_arm_motion
hypothesis: At the verified CLOSE_READY pose, adding the Gazebo-derived 0.006 rad seating preload after the unchanged nominal Close creates a stable bilateral grasp without requiring arm motion or a simulator constraint.
prediction: Nominal Close first produces bilateral contact; q6_contact minus 0.006 rad remains above the frozen safe lower bound; the preloaded grasp then preserves bilateral contact for at least 0.30 s while force stays at or below 11.60 N and cup displacement stays at or below 3 mm.
single_variable: Add seating_preload_rad=0.006 after the same nominal Close used by EXP-073; do not move the arm.
frozen_inputs:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  install_overlay: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-standard
  expected_reset_epoch: 0
  close_target_q6_rad: -0.047608632840292
  seating_preload_rad: 0.006
  safe_q6_lower_rad: -0.059600220867817
  maximum_force_n: 11.60
  maximum_cup_displacement_m: 0.003
  minimum_nominal_bilateral_duration_s: 0.20
  minimum_preloaded_bilateral_duration_s: 0.30
  experiment_script: /tmp/so101_exp077_seating_preload.py
  experiment_script_sha256: 402f5bfb6f5137ddb08fbe7acbf24b58e444cf9f7e35c85c92d279c569c0fd76
preconditions:
  - Planning Scene readback has exact table, pedestal, and plastic_cup primitives/colors and no attached object.
  - The arm matches the EXP-076 CLOSE_READY target within 0.01 rad; q6 is preopened within 0.01 rad of 0.465038.
  - MuJoCo evidence is fresh, unpaused, reset_epoch 0, cup on the source position, no fingertip contact, and only table support.
success_criteria:
  - Both gripper controller actions succeed and q6 remains within the frozen lower bound.
  - Bilateral fingertip contact is continuous for the specified nominal and preloaded dwell windows.
  - Maximum normal force never exceeds 11.60 N and cup displacement from the pre-Close state never exceeds 3 mm.
  - Physics remains unpaused; reset/session provenance does not change; arm_controller/MoveIt execution count remains zero.
  - No weld, equality, adhesion, mocap, teleport, direct object qpos/qvel write, or MoveIt attachment is invoked.
failure_criteria: Any missing bilateral dwell, force/displacement violation, stale evidence, pause/reset/session change, action failure, or provenance mismatch ends EXP-077 before micro-lift.
invalid_criteria: Starting outside the frozen CLOSE_READY state, running a different script hash, using a different overlay/session/reset epoch, or losing evidence makes the experiment INVALID rather than a behavioral failure.
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp077_seating_preload.py
    exit_code: PENDING
evidence_root: /tmp/so101-task13-standard
runtime_start:
  time: 2026-08-12T01:28:00+08:00
  precondition_readback: Controller set active; exact Planning Scene readback passed; CUA screenshot f73366ca849c060f3e86ef51f80a2b7ddf61ad3d02c29a63d71bcfdf1d3f335b shows RViz and MuJoCo side by side at CLOSE_READY; current session/reset/joint/cup/contact state matches CP-111; script hash matches the frozen input.
decision: PENDING. Preconditions and provenance passed; this state transition occurs before both Close and seating-preload controller actions.
next_experiment: EXP-078 only if EXP-077 is VALID success; otherwise stop and recover through the qualified ResetWorld transaction.
```

## Experiment EXP-077 Terminal Result

```yaml
experiment_id: EXP-077
status: VALID
terminal_result: SEATING_PRELOAD_PROVED
terminal_time: 2026-08-12T01:28:20+08:00
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp077_seating_preload.py
    exit_code: 0
result:
  before_close_joints_rad: [-0.00011890242342363529, 0.4726820103356005, 0.21491690296171834, 0.854974398870263, 0.0006620704549954623, 0.46503648701827793]
  before_close_cup_position_world_m: [0.019997553643484413, -0.28000130486677305, 0.16490533251860776]
  nominal_close_q6_rad: -0.04760628697865648
  preload_target_q6_rad: -0.05360628697865648
  seated_actual_q6_rad: -0.05356636830053336
  nominal_bilateral_samples: 27
  preloaded_bilateral_samples: 27
  seated_left_contact_count: 3
  seated_right_contact_count: 4
  nominal_maximum_normal_force_n: 0.2510282790449008
  seated_maximum_normal_force_n: 0.3198435404010932
  cup_displacement_m: [0.0000013275327881701049, 0.00132502300637527, 0.00000035266788878107747]
  cup_displacement_norm_m: 0.001325023718331752
  final_reset_epoch: 0
  physics_paused: false
  physics_pause_calls: 0
  simulator_constraint_calls: 0
  direct_object_state_writes: 0
  moveit_attach_calls: 0
visual_evidence:
  before: /tmp/so101-task13-standard/before-exp077-cua.png
  before_sha256: f73366ca849c060f3e86ef51f80a2b7ddf61ad3d02c29a63d71bcfdf1d3f335b
  after: /tmp/so101-task13-standard/after-exp077-cua.png
  after_sha256: 34e8cac997c617a3cad24e76eba97c9da9e0aab26b80cb74b49f6d5410054a2d
  observation: RViz and MuJoCo remain side by side; the arm pose is unchanged and the cup remains upright on the table. The view resolves the fingers at the cup rim but cannot by itself prove pad contact. Atomic MuJoCo evidence independently proves opposing fixed/moving fingertip-pad contacts against wall_near_collision.
evidence:
  result: /tmp/so101-task13-standard/exp077-seating-preload.json
  result_sha256: 3e4b6297f0e851c75ec91fdce31831cc1d6610c8c7846b7b6e1f440034aeb0a4
  log: /tmp/so101-task13-standard/exp077-seating-preload.log
  log_sha256: 643e4019ff2465ffb545e15d98bd6814fb8b71413a4d2f895482ca343449dbe4
decision: KEEP VALID. The seating-preload boundary is sufficient for a stationary physical wall pinch and authorizes only the separately preregistered 2 mm micro-lift.
```

## Checkpoint CP-112

```yaml
checkpoint_id: CP-112
checkpoint_time: 2026-08-12T01:30:00+08:00
last_valid_experiment: EXP-077
current_hypothesis: The stationary preloaded wall pinch can lift the cup by the frozen 2 mm micro-lift target without lateral slip or table support.
working_tree_status: Same intentional Task 13/14 and plan/ledger dirty set at HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected src/so101_gazebo_demo_py tracked status remains empty.
owned_processes: The unchanged so101-mujoco-gui stack remains live in ROS_DOMAIN_ID 149 and session so101-task13-standard; codex-cua is used only for passive CUA snapshots.
confirmed_conclusions:
  - The 0.006 rad seating preload creates continuous bilateral fingertip contact at approximately 0.320 N maximum normal force without arm motion.
  - The cup moved 1.325 mm laterally but remained on the table, within the frozen 3 mm pre-lift boundary.
  - Physics remained running; no simulator constraint, object-state write, MoveIt attachment, or arm trajectory occurred.
open_risks:
  - The cup has not yet left the table; visual evidence cannot substitute for the upcoming object-z/table-contact gate.
  - MoveIt still represents plastic_cup as a world object and must change it to a collision-only attachment after confirming the physical grasp and before planning arm motion.
next_command: Verify /tmp/so101_exp078_micro_lift.py hash and current preloaded bilateral state, then execute only the 2 mm micro-lift experiment.
```

## Experiment EXP-078

```yaml
experiment_id: EXP-078
prior_experiment: EXP-077 VALID seating preload
status: RUNNING
lifecycle: CONTINUE_OWNED_GUI_STACK_PHYSICAL_MICRO_LIFT
run_mode: attach_collision_shadow_then_execute_2mm_micro_lift
hypothesis: The verified preloaded cup-wall pinch physically raises the cup by 2 mm while preserving bilateral contact, with no simulator-side attachment or object-state write.
prediction: After MoveIt changes plastic_cup from world membership to a gripper collision shadow, the fixed micro-lift target executes with start drift at or below 0.01 rad; cup z rises 1.5-2.5 mm, lateral drift stays at or below 1 mm, table support clears, and bilateral contact persists for at least 0.30 s.
single_variable: Execute the frozen 2 mm arm micro-lift from the unchanged EXP-077 preloaded physical grasp; the MoveIt attachment is collision bookkeeping only.
frozen_inputs:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  install_overlay: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-standard
  expected_reset_epoch: 0
  expected_preload_q6_rad: -0.05360628697865648
  micro_lift_target_arm_rad: [-0.0002062266287315138, 0.46262046903357984, 0.21277364017949124, 0.8648894480356747, 0.0005764164414532356]
  maximum_force_n: 11.60
  minimum_physical_lift_m: 0.0015
  maximum_physical_lift_m: 0.0025
  maximum_lateral_drift_m: 0.001
  minimum_post_lift_bilateral_duration_s: 0.30
  maximum_plan_to_execute_drift_rad: 0.01
  experiment_script: /tmp/so101_exp078_micro_lift.py
  experiment_script_sha256: bac94c79ea0bdcfb68c25427951fc226b4a3e516ce8c843160df361bd4c6d8a8
preconditions:
  - Current arm remains within 0.01 rad of CLOSE_READY and q6 remains within 0.01 rad of the verified seating preload.
  - Fresh atomic evidence shows the same session/reset epoch, running physics, bilateral fingertip contact, force within bounds, and the cup still table-supported.
  - Planning Scene initially has plastic_cup in world membership with no attached object.
success_criteria:
  - MoveIt readback shows plastic_cup attached to gripper with touch_links [gripper, jaw] and absent from world membership before planning.
  - The plan is non-empty, starts within 0.01 rad of the fresh arm state, executes successfully, and reaches the frozen arm target within 0.01 rad.
  - Cup z displacement is 1.5-2.5 mm, lateral displacement is at most 1 mm, table_collision is absent, and bilateral contact persists for at least 0.30 s after convergence.
  - Maximum force remains at or below 11.60 N; physics remains running; session/reset provenance remains fixed.
  - No weld, equality, adhesion, mocap, teleport, direct object qpos/qvel write, or MuJoCo-side attachment occurs.
failure_criteria: Any scene-shadow failure, planning/execution failure, start drift, contact loss, force/lift/lateral/table-support violation, stale evidence, pause, reset, or session change stops before transport.
invalid_criteria: Starting outside the verified EXP-077 state, running a different script hash/overlay/session/reset epoch, or missing fresh evidence makes the experiment INVALID.
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp078_micro_lift.py
    exit_code: PENDING
evidence_root: /tmp/so101-task13-standard
runtime_start:
  time: 2026-08-12T01:34:19+08:00
  precondition_readback: Script hash matched; q1-q5 remained at CLOSE_READY, q6=-0.053567 rad; session so101-task13-standard/reset_epoch 0 remained fresh and unpaused; bilateral wall_near_collision contacts remained present at approximately 0.316 N maximum normal force; cup remained table-supported; Planning Scene readback retained exact table/pedestal/plastic_cup world geometry and colors.
decision: PENDING. Preconditions and provenance passed; this state transition occurs before the Planning Scene attachment, MoveIt plan, and arm execution.
next_experiment: A bounded transport experiment only if EXP-078 is VALID success; otherwise recover through the qualified ResetWorld transaction.
```

## Experiment EXP-078 Terminal Result

```yaml
experiment_id: EXP-078
status: VALID
terminal_result: PHYSICAL_MICRO_LIFT_FAILURE_GRIPPER_SLIPPED_ON_CUP_WALL
terminal_time: 2026-08-12T01:34:48+08:00
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp078_micro_lift.py
    exit_code: 1
result:
  moveit_attached_ids: [plastic_cup]
  moveit_world_ids_after_attach: [pedestal, table]
  lift_trajectory_points: 6
  plan_to_execute_drift_rad: 0.000000007315917162657379
  arm_execution_succeeded: true
  final_joint_positions_rad: [-0.00022776510686361472, 0.4631160042473382, 0.21299761594544703, 0.8648150820848761, 0.0004898491567893434, -0.053566920925526354]
  transient_physical_cup_lift_m: 0.0010224025997758457
  required_physical_cup_lift_m: [0.0015, 0.0025]
  settled_cup_position_world_m: [0.020033949175698982, -0.27902969996080207, 0.16490532288843415]
  settled_table_contact: true
  settled_left_contact_count: 3
  settled_right_contact_count: 4
  settled_maximum_normal_force_n: 0.32671832648538424
  final_reset_epoch: 0
  physics_paused: false
  simulator_constraint_calls: 0
  direct_object_state_writes: 0
diagnosis:
  - MoveIt planning and controller execution succeeded and the arm reached the 2 mm micro-lift target.
  - The gripper contact points moved upward with the arm while the cup rose only 1.022 mm transiently, then settled back to table support with bilateral contact still present.
  - This is a physical friction/normal-force failure at the gripper-cup boundary, not a planner, controller, Planning Scene, or reset failure.
  - The frozen 1.5 mm lower bound is not relaxed after the result.
evidence:
  result: /tmp/so101-task13-standard/exp078-micro-lift.json
  result_sha256: d38c119f7170d3e072b4c3f6b2caaffae394d6b80f83b9b58529b45eca638b33
  log: /tmp/so101-task13-standard/exp078-micro-lift.log
  log_sha256: a02a88ec60f27f68d3c440d4bde7f63f2a98eb2584b95760c964efec0dc03acd
decision: KEEP VALID as a physical failure. Do not continue transport. Isolate one additional bounded preload increment before any second lift motion.
```

## Checkpoint CP-113

```yaml
checkpoint_id: CP-113
checkpoint_time: 2026-08-12T01:36:00+08:00
last_valid_experiment: EXP-078
current_hypothesis: The first 0.006 rad seating preload provides bilateral contact but insufficient friction margin; one additional 0.006 rad increment, capped by the existing safe q6 lower bound, may prevent wall slip.
working_tree_status: Same intentional Task 13/14 and plan/ledger dirty set at HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty.
owned_processes: The unchanged GUI stack remains live in domain 149/session so101-task13-standard. The arm is at the EXP-078 endpoint; q6 still holds the first preload; cup remains table-supported; Planning Scene retains plastic_cup as an attached collision shadow.
confirmed_conclusions:
  - EXP-078 separates planning from physics: plan/execute passed with negligible start drift, but the cup slipped and returned to the table.
  - Current atomic evidence remains fresh, unpaused, reset_epoch 0, bilateral, and below the force abort boundary.
disproven_routes:
  - A single 0.006 rad seating preload followed by the frozen 2 mm arm micro-lift does not clear the table under this MuJoCo fingerprint.
open_risks:
  - Additional preload could displace or over-compress the cup and must be tested with no arm motion first.
  - The next q6 target is close to, but does not cross, the frozen safe lower bound.
next_command: Verify and preregister /tmp/so101_exp079_additional_preload.py, then command only the additional q6 preload increment.
```

## Experiment EXP-079

```yaml
experiment_id: EXP-079
prior_experiment: EXP-078 VALID physical slip failure
status: RUNNING
lifecycle: CONTINUE_OWNED_GUI_STACK_ADDITIONAL_PRELOAD_ONLY
run_mode: add_second_0p006rad_preload_no_arm_motion
hypothesis: One additional 0.006 rad preload increment, capped at the existing safe q6 lower bound, increases the wall-pinch normal force while preserving bilateral contact and bounded cup displacement.
prediction: q6 moves from approximately -0.053567 rad to approximately -0.059567 rad without crossing -0.059600220867817; bilateral contact remains stable for at least 0.30 s, force stays at or below 11.60 N, and cup displacement during the preload remains at or below 3 mm.
single_variable: Add one 0.006 rad q6 preload increment; do not move the arm or alter friction, model, planning, or simulator state.
frozen_inputs:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  install_overlay: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-standard
  expected_reset_epoch: 0
  expected_arm_state_rad: [-0.0002062266287315138, 0.46262046903357984, 0.21277364017949124, 0.8648894480356747, 0.0005764164414532356]
  expected_q6_rad: -0.05360628697865648
  preload_increment_rad: 0.006
  safe_q6_lower_rad: -0.059600220867817
  maximum_force_n: 11.60
  maximum_cup_displacement_m: 0.003
  minimum_bilateral_duration_s: 0.30
  experiment_script: /tmp/so101_exp079_additional_preload.py
  experiment_script_sha256: 28df26eacc26ee84940f1c92ff5cad6d959d6ad9dcbd095efad08f9b1036ba6a
preconditions:
  - Arm remains within 0.01 rad of the EXP-078 endpoint and q6 remains within 0.01 rad of the first preload.
  - Fresh evidence remains unpaused at session so101-task13-standard/reset_epoch 0 with bilateral wall contact, bounded force, and table support.
  - Planning Scene still reports plastic_cup as the gripper collision shadow; no simulator attachment exists.
success_criteria:
  - Gripper controller action succeeds and actual q6 does not cross the frozen safe lower bound.
  - Bilateral contact persists for at least 0.30 s after convergence, maximum force stays at or below 11.60 N, and cup displacement stays at or below 3 mm.
  - No arm trajectory, physics pause/reset, simulator constraint, object-state write, or Planning Scene mutation occurs.
failure_criteria: Any action failure, safe-lower-bound violation, contact loss, force/displacement violation, stale evidence, pause, reset, or session change stops before a second micro-lift.
invalid_criteria: Starting outside the EXP-078 endpoint/EXP-077 preload state, using a different script hash/overlay/session/reset epoch, or missing fresh evidence makes the experiment INVALID.
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp079_additional_preload.py
    exit_code: PENDING
evidence_root: /tmp/so101-task13-standard
runtime_start:
  time: 2026-08-12T01:38:16+08:00
  precondition_readback: Script hash matched; q1-q5 remained at the EXP-078 arm endpoint; q6=-0.053567 rad; fresh unpaused session/reset evidence retained 3 left and 4 right wall contacts at approximately 0.327 N maximum normal force with the cup table-supported; Planning Scene membership was not changed after EXP-078.
decision: PENDING. Preconditions and provenance passed; this state transition occurs before the additional gripper-controller action.
next_experiment: A separately preregistered incremental micro-lift only if EXP-079 is VALID success; otherwise recover through the qualified ResetWorld transaction.
```

## Experiment EXP-079 Terminal Result

```yaml
experiment_id: EXP-079
status: VALID
terminal_result: ADDITIONAL_PRELOAD_PROVED
terminal_time: 2026-08-12T01:38:36+08:00
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp079_additional_preload.py
    exit_code: 0
result:
  q6_before_rad: -0.0535669207912796
  preload_target_q6_rad: -0.0595669207912796
  seated_actual_q6_rad: -0.059447660992339564
  safe_q6_lower_rad: -0.059600220867817
  before_bilateral_samples: 31
  seated_bilateral_samples: 27
  seated_left_contact_count: 3
  seated_right_contact_count: 4
  before_maximum_normal_force_n: 0.326746164584091
  seated_maximum_normal_force_n: 0.7880521553461874
  cup_displacement_m: [-0.00000019787980951729844, 0.0002397141753352483, 0.0000005674840344027654]
  cup_displacement_norm_m: 0.00023971492871994118
  final_reset_epoch: 0
  physics_paused: false
  physics_pause_calls: 0
  simulator_constraint_calls: 0
  direct_object_state_writes: 0
  moveit_attach_calls: 0
evidence:
  result: /tmp/so101-task13-standard/exp079-additional-preload.json
  result_sha256: 564e9e4ee889222c199412e028bc713ecab59f5940cb7db73277abee063715b2
  log: /tmp/so101-task13-standard/exp079-additional-preload.log
  log_sha256: 914413883d553165009227982740e561c944fc2241883cb3b8e09632a097e290
decision: KEEP VALID. The additional preload increases normal-force margin without unsafe displacement and authorizes only the separately preregistered incremental 2 mm micro-lift.
```

## Checkpoint CP-114

```yaml
checkpoint_id: CP-114
checkpoint_time: 2026-08-12T01:39:00+08:00
last_valid_experiment: EXP-079
current_hypothesis: The approximately 0.788 N stronger preloaded pinch can prevent the wall slip observed in EXP-078 during one additional 2 mm arm lift.
working_tree_status: Same intentional Task 13/14 and plan/ledger dirty set at HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty.
owned_processes: The unchanged domain 149/session so101-task13-standard stack remains live; arm at EXP-078 endpoint; q6 holds the additional preload; cup remains table-supported; Planning Scene collision shadow remains attached.
confirmed_conclusions:
  - The second 0.006 rad preload increment raises maximum normal force from approximately 0.327 N to 0.788 N.
  - The increment moves the cup only 0.240 mm and preserves 3 left/4 right contacts with running physics and reset_epoch 0.
open_risks:
  - Stronger static contact does not yet prove sufficient vertical friction; the next experiment must use object z and table-contact evidence.
next_command: Verify and preregister /tmp/so101_exp080_incremental_micro_lift.py, then execute only the additional 2 mm arm target.
```

## Experiment EXP-080

```yaml
experiment_id: EXP-080
prior_experiment: EXP-079 VALID additional preload; EXP-078 VALID slip failure
status: RUNNING
lifecycle: CONTINUE_OWNED_GUI_STACK_INCREMENTAL_MICRO_LIFT
run_mode: execute_second_2mm_arm_increment
hypothesis: The stronger preloaded cup-wall pinch physically raises the cup during one additional 2 mm arm micro-lift while preserving bilateral contact and clearing table support.
prediction: From the EXP-078 arm endpoint, the next target along the same local joint-space lift direction executes with start drift at or below 0.01 rad; cup z rises 1.5-2.5 mm, lateral drift stays at or below 1 mm, table support clears, and bilateral contact persists for at least 0.30 s.
single_variable: Execute one additional 2 mm arm lift under the unchanged EXP-079 preload; do not change q6, friction, model, scene membership, or simulator state.
frozen_inputs:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  install_overlay: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-standard
  expected_reset_epoch: 0
  previous_arm_target_rad: [-0.0002062266287315138, 0.46262046903357984, 0.21277364017949124, 0.8648894480356747, 0.0005764164414532356]
  expected_q6_rad: -0.0595669207912796
  incremental_lift_target_arm_rad: [-0.0002059614124630276, 0.4530466639711597, 0.21089465616398247, 0.8748565203763494, 0.0005761294179064712]
  maximum_force_n: 11.60
  minimum_physical_lift_m: 0.0015
  maximum_physical_lift_m: 0.0025
  maximum_lateral_drift_m: 0.001
  minimum_post_lift_bilateral_duration_s: 0.30
  maximum_plan_to_execute_drift_rad: 0.01
  experiment_script: /tmp/so101_exp080_incremental_micro_lift.py
  experiment_script_sha256: 927e5ae5e59bb3b357227bd69443fd5777938f39c73cc6c6073d4dd67955f4fc
preconditions:
  - Current arm remains within 0.01 rad of the EXP-078 endpoint and q6 remains within 0.01 rad of the EXP-079 preload.
  - Fresh evidence remains unpaused at the same session/reset epoch with bilateral contact, force within bounds, and the cup table-supported.
  - Planning Scene already reports plastic_cup attached to gripper and absent from world membership; the experiment performs no scene mutation.
success_criteria:
  - Existing Planning Scene collision-shadow membership is read back before planning.
  - The plan is non-empty, starts within 0.01 rad of the fresh arm state, executes successfully, and reaches the incremental target within 0.01 rad.
  - Cup z displacement is 1.5-2.5 mm, lateral displacement is at most 1 mm, table_collision is absent, and bilateral contact persists for at least 0.30 s after convergence.
  - Maximum force remains at or below 11.60 N; q6 remains unchanged; physics remains running; session/reset provenance remains fixed.
  - No Planning Scene mutation, weld, equality, adhesion, mocap, teleport, direct object qpos/qvel write, or MuJoCo-side attachment occurs.
failure_criteria: Any scene-readback failure, planning/execution failure, start drift, contact loss, force/lift/lateral/table-support violation, stale evidence, pause, reset, or session change stops before transport.
invalid_criteria: Starting outside the EXP-078/079 state, using a different script hash/overlay/session/reset epoch, or missing fresh evidence makes the experiment INVALID.
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp080_incremental_micro_lift.py
    exit_code: PENDING
evidence_root: /tmp/so101-task13-standard
runtime_start:
  time: 2026-08-12T01:41:06+08:00
  precondition_readback: Script hash matched; q1-q5 remained at the EXP-078 endpoint, q6=-0.059448 rad; session/reset evidence remained fresh and unpaused with 3 left/4 right wall contacts at approximately 0.788 N and table support; the existing attached collision shadow was preserved from EXP-078.
decision: PENDING. Preconditions and provenance passed; this state transition occurs before the MoveIt plan and arm execution.
next_experiment: A bounded transport experiment only if EXP-080 is VALID success; otherwise recover through the qualified ResetWorld transaction.
```

## Experiment EXP-080 Terminal Result

```yaml
experiment_id: EXP-080
status: VALID
terminal_result: INCREMENTAL_2MM_LIFT_FAILURE_CUP_REMAINED_TABLE_SUPPORTED
terminal_time: 2026-08-12T01:41:30+08:00
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp080_incremental_micro_lift.py
    exit_code: 1
result:
  moveit_attached_ids_before_incremental_lift: [plastic_cup]
  moveit_world_ids_before_incremental_lift: [pedestal, table]
  lift_trajectory_points: 6
  plan_to_execute_drift_rad: 0.000000011845965718629758
  arm_execution_succeeded: true
  final_joint_positions_rad: [-0.00013077478451799392, 0.45359180867627663, 0.21111100554281248, 0.8748310618542893, 0.0005773340904787511, -0.05944748134876294]
  transient_physical_cup_lift_m: 0.0011991071505775552
  required_physical_cup_lift_m: [0.0015, 0.0025]
  settled_cup_position_world_m: [0.020014959710363617, -0.2790812760248211, 0.16490535545801602]
  settled_table_contact: true
  settled_left_contact_count: 3
  settled_right_contact_count: 4
  settled_maximum_normal_force_n: 0.8041681024961073
  final_reset_epoch: 0
  physics_paused: false
diagnosis:
  - The stronger preload improved transient physical lift from 1.022 mm to 1.199 mm while plan/execute remained successful.
  - The cup still returned to table support; therefore force margin alone is not sufficient for a 2 mm arm increment.
  - q6 is already near the frozen safe lower bound, so further preload is not an admissible next variable.
  - The measured transfer ratio supports testing one 3 mm arm increment while keeping q6, model, friction, scene, and physics unchanged.
evidence:
  result: /tmp/so101-task13-standard/exp080-incremental-micro-lift.json
  result_sha256: 1188abf73da10da051144a8649cd60c052ad7e93a99919e3f8da7f071ca70ff1
  log: /tmp/so101-task13-standard/exp080-incremental-micro-lift.log
  log_sha256: 051c6932fa2ce934823bc4742241cec76f9aac33999b8a37d81edeabcead8227
decision: KEEP VALID as a physical failure. Do not continue transport. Test one larger arm increment without changing the near-limit preload.
```

## Checkpoint CP-115

```yaml
checkpoint_id: CP-115
checkpoint_time: 2026-08-12T01:43:00+08:00
last_valid_experiment: EXP-080
current_hypothesis: With the stronger preload fixed, a 3 mm arm increment should produce approximately 1.8 mm physical cup lift and clear table support.
working_tree_status: Same intentional Task 13/14 and plan/ledger dirty set at HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty.
owned_processes: The unchanged domain 149/session so101-task13-standard stack remains live; arm at EXP-080 endpoint; q6 holds near the safe lower bound; cup remains table-supported; Planning Scene collision shadow remains attached.
confirmed_conclusions:
  - Two independent arm lift executions planned and executed successfully but produced 1.022 mm and 1.199 mm transient cup lift, both below the frozen 1.5 mm gate.
  - Stronger preload improved the physical transfer ratio, but the 2 mm arm increment is too small to clear table support under this fingerprint.
disproven_routes:
  - Repeating another 2 mm increment under the same q6 would not provide a new discriminating variable.
open_risks:
  - A 3 mm increment may still slip or create lateral motion; it remains bounded by the same force/contact/session gates.
next_command: Verify and preregister /tmp/so101_exp081_incremental_3mm_lift.py, then execute only the 3 mm arm increment.
```

## Experiment EXP-081

```yaml
experiment_id: EXP-081
prior_experiment: EXP-080 VALID 2 mm physical failure
status: RUNNING
lifecycle: CONTINUE_OWNED_GUI_STACK_INCREMENTAL_3MM_LIFT
run_mode: execute_incremental_3mm_arm_lift
hypothesis: With the stronger preload unchanged, a 3 mm arm increment yields at least 1.5 mm physical cup lift, clears table support, and preserves bilateral contact.
prediction: The frozen target executes with start drift at or below 0.01 rad; cup z rises 1.5-3.5 mm, lateral drift stays at or below 1 mm, table support clears, and bilateral contact persists for at least 0.30 s.
single_variable: Increase the arm lift increment from 2 mm to 3 mm; keep q6, friction, model, scene membership, and simulator state unchanged.
frozen_inputs:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  install_overlay: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-standard
  expected_reset_epoch: 0
  previous_arm_target_rad: [-0.0002059614124630276, 0.4530466639711597, 0.21089465616398247, 0.8748565203763494, 0.0005761294179064712]
  expected_q6_rad: -0.0595669207912796
  incremental_lift_target_arm_rad: [-0.0002055635880602983, 0.43868595637752946, 0.20807618014071933, 0.8898071288873615, 0.0005756988825863246]
  maximum_force_n: 11.60
  minimum_physical_lift_m: 0.0015
  maximum_physical_lift_m: 0.0035
  maximum_lateral_drift_m: 0.001
  minimum_post_lift_bilateral_duration_s: 0.30
  maximum_plan_to_execute_drift_rad: 0.01
  experiment_script: /tmp/so101_exp081_incremental_3mm_lift.py
  experiment_script_sha256: e409c9717fdcb71f6356faf47e89780d90f97ecba42bb2d8c9d7ccdad4a7f223
preconditions:
  - Current arm remains within 0.01 rad of the EXP-080 endpoint and q6 remains within 0.01 rad of the EXP-079 preload.
  - Fresh evidence remains unpaused at the same session/reset epoch with bilateral contact, force within bounds, and the cup table-supported.
  - Planning Scene already reports plastic_cup attached to gripper and absent from world membership; the experiment performs no scene mutation.
success_criteria:
  - Existing Planning Scene collision-shadow membership is read back before planning.
  - The plan is non-empty, starts within 0.01 rad of the fresh arm state, executes successfully, and reaches the incremental target within 0.01 rad.
  - Cup z displacement is 1.5-3.5 mm, lateral displacement is at most 1 mm, table_collision is absent, and bilateral contact persists for at least 0.30 s after convergence.
  - Maximum force remains at or below 11.60 N; q6 remains unchanged; physics remains running; session/reset provenance remains fixed.
  - No Planning Scene mutation, weld, equality, adhesion, mocap, teleport, direct object qpos/qvel write, or MuJoCo-side attachment occurs.
failure_criteria: Any scene-readback failure, planning/execution failure, start drift, contact loss, force/lift/lateral/table-support violation, stale evidence, pause, reset, or session change stops before transport.
invalid_criteria: Starting outside the EXP-080/079 state, using a different script hash/overlay/session/reset epoch, or missing fresh evidence makes the experiment INVALID.
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp081_incremental_3mm_lift.py
    exit_code: PENDING
evidence_root: /tmp/so101-task13-standard
runtime_start:
  time: 2026-08-12T01:44:02+08:00
  precondition_readback: Script hash matched; q1-q5 remained at the EXP-080 endpoint, q6=-0.059447 rad; fresh unpaused session/reset evidence retained 3 left/4 right wall contacts at approximately 0.804 N and table support; the attached collision shadow remained the expected scene state.
decision: PENDING. Preconditions and provenance passed; this state transition occurs before the MoveIt plan and arm execution.
next_experiment: A bounded transport experiment only if EXP-081 is VALID success; otherwise stop and reassess grasp geometry rather than repeating lift increments.
```

## Experiment EXP-081 Terminal Result

```yaml
experiment_id: EXP-081
status: VALID
terminal_result: INCREMENTAL_3MM_PHYSICAL_LIFT_PROVED
terminal_time: 2026-08-12T01:46:51+08:00
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp081_incremental_3mm_lift.py
    exit_code: 0
result:
  moveit_attached_ids_before_incremental_lift: [plastic_cup]
  moveit_world_ids_before_incremental_lift: [pedestal, table]
  lift_trajectory_points: 6
  plan_to_execute_drift_rad: 0.0000002504703686880428
  arm_execution_succeeded: true
  final_joint_positions_rad: [-0.0002095371845950378, 0.43925280921578225, 0.20839384089198643, 0.8898089626155721, 0.0006091768252660451, -0.05944518916279066]
  physical_cup_lift_m: 0.0020966948179507727
  physical_lateral_drift_m: 0.00038143508538649617
  settled_cup_position_world_m: [0.02003159096475189, -0.2794623291149958, 0.16700204963252638]
  settled_table_contact: false
  settled_left_contact_count: 3
  settled_right_contact_count: 4
  settled_maximum_normal_force_n: 0.8304586277017592
  final_reset_epoch: 0
  physics_paused: false
  physics_pause_calls: 0
  simulator_constraint_calls: 0
  direct_object_state_writes: 0
diagnosis:
  - The frozen 3 mm arm increment produced a 2.097 mm physical cup lift, inside the preregistered 1.5-3.5 mm gate.
  - Table support cleared and 3 left/4 right fingertip contacts persisted for the post-lift stable window, so the transfer is physical rather than a Planning Scene or simulator attachment artifact.
  - Force remained below 0.84 N, leaving substantial margin below the unchanged 11.60 N safety gate.
evidence:
  result: /tmp/so101-task13-standard/exp081-incremental-3mm-lift.json
  result_sha256: 332782f1ff3ebe96d326c9348479907b152d43d673c81fb44069c8bcf65bff00
  log: /tmp/so101-task13-standard/exp081-incremental-3mm-lift.log
  log_sha256: 662a93679ee57c63b6ec63f8f14e02277efea811f3e2061a4a3268d96a6a2e5e
decision: KEEP VALID as the first constraint-free physical micro-lift success. Continue only through a separately preregistered policy LIFT waypoint.
```

## Checkpoint CP-116

```yaml
checkpoint_id: CP-116
checkpoint_time: 2026-08-12T01:46:51+08:00
last_valid_experiment: EXP-081
current_hypothesis: The stronger physical grasp can carry the cup from the verified micro-lift into policy LIFT waypoint 1 without contact loss or hidden simulator assistance.
working_tree_status: Same intentional Task 13/14 and plan/ledger dirty set at HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty.
owned_processes: The unchanged domain 149/session so101-task13-standard stack remains live; arm at EXP-081 endpoint; q6 holds near -0.05945 rad; cup is physically clear of the table; Planning Scene collision shadow remains attached.
confirmed_conclusions:
  - MuJoCo physical evidence, not MoveIt scene state, proves a 2.097 mm cup lift with table support absent and bilateral grasp contact retained.
  - The unchanged arm controller and MoveIt execution path remain healthy with negligible plan-to-execute drift.
disproven_routes:
  - No additional preload or repeated micro-lift increment is needed before testing the first formal policy LIFT waypoint.
open_risks:
  - The larger policy waypoint may expose slip or lateral motion that the 3 mm micro-lift could not reveal.
next_command: Verify and preregister /tmp/so101_exp082_policy_lift_waypoint1.py, then execute only policy LIFT waypoint 1.
```

## Experiment EXP-082

```yaml
experiment_id: EXP-082
prior_experiment: EXP-081 VALID physical micro-lift success
status: PLANNED
lifecycle: CONTINUE_OWNED_GUI_STACK_POLICY_LIFT_WAYPOINT1
run_mode: execute_policy_lift_waypoint1
hypothesis: The verified stronger preload physically carries the cup through policy LIFT waypoint 1 while bilateral contact and force bounds remain valid.
prediction: The frozen waypoint executes with start drift at or below 0.01 rad; cup z rises by 5-100 mm, lateral displacement remains at or below 30 mm, table support remains absent, and bilateral contact persists for at least 0.30 s.
single_variable: Replace the successful 3 mm micro-lift target with the first frozen LIFT waypoint; keep q6, model, friction, controller, scene membership, simulator session, and reset epoch unchanged.
frozen_inputs:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  install_overlay: /tmp/so101-debug-mujoco-task13-reboot-UKG4mIaz/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-standard
  expected_reset_epoch: 0
  previous_arm_target_rad: [-0.0002055635880602983, 0.43868595637752946, 0.20807618014071933, 0.8898071288873615, 0.0005756988825863246]
  expected_q6_rad: -0.0595669207912796
  lift_waypoint1_arm_rad: [-0.000284124852, 0.381814591288, 0.272246878070, 0.916741182602, -0.000291565154]
  maximum_force_n: 11.60
  minimum_physical_lift_m: 0.005
  maximum_physical_lift_m: 0.10
  maximum_lateral_displacement_m: 0.03
  minimum_post_lift_bilateral_duration_s: 0.30
  maximum_plan_to_execute_drift_rad: 0.01
  experiment_script: /tmp/so101_exp082_policy_lift_waypoint1.py
  experiment_script_sha256: 8c7909e9fdb6666c7a6413571e2d0e6c3f9a5a031aece3b59effbb91fa98fa48
preconditions:
  - Current arm remains within 0.01 rad of the EXP-081 endpoint and q6 remains within 0.01 rad of the EXP-079 stronger preload.
  - Fresh evidence remains unpaused at the same session/reset epoch with bilateral contact, force within bounds, and no cup/table contact.
  - Planning Scene already reports plastic_cup attached to gripper and absent from world membership; the experiment performs no scene mutation.
success_criteria:
  - Existing Planning Scene collision-shadow membership is read back before planning.
  - The plan is non-empty, starts within 0.01 rad of the fresh arm state, executes successfully, and reaches LIFT waypoint 1 within 0.01 rad.
  - Cup z displacement is 5-100 mm, lateral displacement is at most 30 mm, table_collision remains absent, and bilateral contact persists for at least 0.30 s after convergence.
  - Maximum force remains at or below 11.60 N; q6 remains unchanged; physics remains running; session/reset provenance remains fixed.
  - No Planning Scene mutation, weld, equality, adhesion, mocap, teleport, direct object qpos/qvel write, or MuJoCo-side attachment occurs.
failure_criteria: Any scene-readback failure, planning/execution failure, start drift, contact loss, force/lift/lateral/table-support violation, stale evidence, pause, reset, or session change stops before the remaining LIFT waypoints.
invalid_criteria: Starting outside the EXP-081 state, using a different script hash/overlay/session/reset epoch, or missing fresh evidence makes the experiment INVALID.
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp082_policy_lift_waypoint1.py
    exit_code: PENDING
evidence_root: /tmp/so101-task13-standard
decision: PENDING. Execute only after the script hash, current joints, physical grasp, scene membership, and simulator provenance are read back and EXP-082 is transitioned to RUNNING.
next_experiment: Remaining LIFT waypoints only if EXP-082 is VALID success; otherwise recover through the qualified ResetWorld transaction.
```

## Experiment EXP-082 Terminal Result

```yaml
experiment_id: EXP-082
status: VALID
terminal_result: PRECONDITION_FAILURE_LONG_HOLD_SLIP
terminal_time: 2026-08-12T01:50:54+08:00
commands:
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp082_policy_lift_waypoint1.py
    exit_code: NOT_RUN
readback:
  current_joint_positions_rad: [-0.0002097396399154292, 0.4392237728669602, 0.20837618605608269, 0.8898084733152872, 0.0006093203380582766, -0.059446834210361704]
  publisher_sequence: 201158
  simulation_step: 201158
  reset_epoch: 0
  simulation_session_id: so101-task13-standard
  physics_paused: false
  cup_position_world_m: [0.020030936196574475, -0.279474804905543, 0.16490537262223293]
  table_contact: true
  left_contact_count: 3
  right_contact_count: 4
  maximum_normal_force_n: 0.8292155129856251
diagnosis:
  - The arm and q6 remained at the verified EXP-081 endpoint, but the cup returned from z=0.167002 m to its table-supported z=0.164905 m during the longer unpaused hold.
  - Bilateral wall contacts and normal force persisted, isolating the failure to gravity-driven tangential slip rather than contact loss, controller drift, or Planning Scene state.
  - Source inspection found MuJoCo cup collision friction 0.7 and no fingertip-specific TPU friction, while the Gazebo task contract defines cup friction 1.2 and TPU axial/transverse coefficients 3.0/1.2.
decision: KEEP VALID as a no-motion precondition failure. Do not execute policy LIFT waypoint 1 on a grasp that cannot remain suspended. Correct the explicit MuJoCo material parity, then use the qualified ResetWorld path and replay from the task start.
```

## Checkpoint CP-117

```yaml
checkpoint_id: CP-117
checkpoint_time: 2026-08-12T01:50:54+08:00
last_valid_experiment: EXP-082
current_hypothesis: The missing Gazebo TPU-on-plastic axial friction contract, not MoveIt or ros2_control, causes the slow cup slip.
working_tree_status: Same intentional Task 13/14 and plan/ledger dirty set at HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty.
owned_processes: The unchanged domain 149/session so101-task13-standard GUI stack remains live and unpaused; no EXP-082 motion command was sent.
confirmed_conclusions:
  - A 0.30 s micro-lift observation is insufficient as a stable-hold gate for this workflow; the next positive hold gate must cover a materially longer window before transport.
  - MuJoCo task-scene friction is not at parity with the Gazebo light-cup material contract even though mass and geometry are at parity.
disproven_routes:
  - Executing the formal transport path immediately after a transient micro-lift would hide a reproducible long-hold slip and is rejected.
open_risks:
  - MuJoCo geom friction is isotropic, whereas the Gazebo pad contract distinguishes axial 3.0 from transverse 1.2; the parity implementation must document and test the chosen conservative mapping.
next_command: Add a tested fingertip/cup friction mapping in the MuJoCo model, rebuild the overlay, restart through the owned GUI scripts, ResetWorld, and preregister the replay as EXP-083.
```

## Experiment EXP-083

```yaml
experiment_id: EXP-083
prior_experiment: EXP-082 VALID no-motion long-hold precondition failure
status: RUNNING
lifecycle: FRICTION_PARITY_RESET_REPLAY_AND_LONG_HOLD
run_mode: execute_exact_qualified_grasp_replay_with_10s_hold
hypothesis: Mapping the Gazebo light-cup material contract into MuJoCo eliminates the slow gravity-driven cup slip without changing mass, geometry, preload, trajectory, controller, or attachment policy.
prediction: After the qualified ResetWorld transaction and exact approach/preload/micro-lift replay, the cup remains 1.5-3.5 mm above its pre-lift height with no table contact and continuous bilateral fingertip contact for 10.0 s.
single_variable: MuJoCo contact friction only: cup sliding friction 0.7 -> 1.2 and the 13 TPU fingertip-pad collisions receive sliding friction 3.0; geometry, mass, inertias, q6 bounds, controller gains, policy waypoints, preload increments, physics timestep, and gravity remain unchanged.
mapping_rationale:
  - Gazebo plastic-cup collision friction is 1.2.
  - Gazebo TPU pad friction is axial 3.0 and transverse 1.2; MuJoCo geom friction is isotropic, so the load-bearing vertical/axial coefficient 3.0 is applied only to the fingertip pad collision geoms and the limitation is retained as an explicit model note for later calibration.
frozen_inputs:
  source_head: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  install_overlay: /tmp/so101-friction-20260812/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-friction-parity
  expected_initial_reset_epoch: 0
  robot_mjcf_sha256: 846b460b4933924a64e3eec6ac3dc7a0f9d0f56baf73389e58ffaf6bcef79430
  scene_mjcf_sha256: aa830e733f9c9715c2e20dc148c70102f00a340e3218bf587fb150360d1b7ef5
  motion_policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
  replay_scripts:
    - [/tmp/so101_exp083_077_seating_preload.py, 34d01fc0d1b65016aa8a376913ecc96c11c7ec6148e2499894e3c5c25f3cc9a9]
    - [/tmp/so101_exp083_078_micro_lift.py, fa01c669a2a2c2e896a702e00e6da5fe51ecaaab98672f281aed180a496e3dad]
    - [/tmp/so101_exp083_079_additional_preload.py, 8d0114effa94bf8285ad2066b2f0ea2d3f6c3bd7a2e2ac48f71dd0b81a96a2ed]
    - [/tmp/so101_exp083_080_incremental_micro_lift.py, 740d94acb0e85a4b475594c6a567d41c7a11b76cffc76bc14281f8f9b0a7f781]
    - [/tmp/so101_exp083_081_incremental_3mm_lift.py, 06dc8470b15245d18d4c7c1a9f7b2a0c6cefbd6b7a042f101b9291781c8a4fd4]
  maximum_force_n: 11.60
  long_hold_duration_s: 10.0
  minimum_physical_lift_m: 0.0015
  maximum_physical_lift_m: 0.0035
  maximum_lateral_drift_m: 0.001
preconditions:
  - Targeted geometry/material tests pass, source and installed MJCF hashes match, the standard fork dependency is unchanged, and protected Gazebo tracked status is empty.
  - The owned GUI stack reports session so101-task13-friction-parity, reset epoch 0, unpaused physics, active arm/gripper/joint-state controllers, and task-start cup/table state.
  - No constraint, weld, adhesion, mocap, teleport, object qpos/qvel write, or MuJoCo-side attachment is introduced.
success_criteria:
  - ResetWorld(task_start) succeeds transactionally; reset epoch increments and fresh evidence plus GUI show the task-start robot and cup.
  - Formal scene_setup readback contains exactly table, pedestal, and 13-primitive plastic_cup with colors; staged_approach reaches CLOSE_READY with no early cup/fingertip contact or cup displacement.
  - The exact EXP-077/078/079/080/081 command sequence replays under the new session with the same two 0.006 rad preload increments and frozen arm targets.
  - The final 3 mm increment yields 1.5-3.5 mm cup lift, at most 1 mm lateral drift, no table contact, continuous bilateral contact for 10.0 s, force at or below 11.60 N, and no reset/pause/session change.
failure_criteria: Any build/provenance mismatch, reset or scene failure, early contact, planning/execution failure, contact/force/lift/lateral/table-support violation, or long-hold slip stops before formal transport.
invalid_criteria: Any unrecorded model/controller/policy/preload/trajectory change, missing script hash, hidden attachment/constraint/write, or missing atomic evidence makes the experiment INVALID.
commands:
  - command: ros2 service call /mujoco_ros2_control_node/reset_world mujoco_ros2_control_msgs/srv/ResetWorld "{keyframe: task_start}"
    exit_code: PENDING
  - command: ros2 run so101_mujoco_demo_py scene_setup
    exit_code: PENDING
  - command: ros2 run so101_mujoco_demo_py staged_approach --mode execute --execute --stop-after DESCEND --simulation-session-id so101-task13-friction-parity --evidence-file /tmp/so101-task13-friction-parity/exp083-staged-approach.json
    exit_code: PENDING
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp083_077_seating_preload.py
    exit_code: PENDING
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp083_078_micro_lift.py
    exit_code: PENDING
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp083_079_additional_preload.py
    exit_code: PENDING
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp083_080_incremental_micro_lift.py
    exit_code: PENDING
  - command: ROS_DOMAIN_ID=149 python3 /tmp/so101_exp083_081_incremental_3mm_lift.py
    exit_code: PENDING
evidence_root: /tmp/so101-task13-friction-parity
runtime_start:
  time: 2026-08-12T01:58:36+08:00
  precondition_readback: Targeted material/geometry compilation tests passed 17/17; protected Gazebo tracked status was empty; source and installed robot/scene MJCF hashes matched; domain 149 reported active arm/gripper/joint-state controllers and fresh unpaused session so101-task13-friction-parity evidence at reset epoch 0.
decision: PENDING. Preconditions and provenance passed; this state transition occurs before ResetWorld, scene mutation, and every motion command.
next_experiment: Policy LIFT waypoint 1 only if EXP-083 is VALID long-hold success; otherwise stop and reassess the contact-model mapping.
```

## Experiment EXP-083 Terminal Result

```yaml
experiment_id: EXP-083
status: VALID
terminal_result: RESET_SUCCEEDED_VISUALLY_BUT_ATOMIC_EVIDENCE_DID_NOT_RESUME
terminal_time: 2026-08-12T02:12:20+08:00
commands:
  - command: ros2 service call /mujoco_ros2_control_node/reset_world mujoco_ros2_control_msgs/srv/ResetWorld "{keyframe: task_start}"
    exit_code: 0_AFTER_FORMAL_DEACTIVATE_PAUSE_RESET_RESUME_ACTIVATE_TRANSACTION
  - command: ros2 run so101_mujoco_demo_py scene_setup
    exit_code: 0
  - command: ros2 run so101_mujoco_demo_py staged_approach --mode execute --execute --stop-after DESCEND --simulation-session-id so101-task13-friction-parity --evidence-file /tmp/so101-task13-friction-parity/exp083-staged-approach.json
    exit_code: 1
result:
  reset_service_success: true
  reset_visual_success: true
  joint_states_after_reset_hz: approximately 100
  evidence_publisher_count_after_reset: 1
  evidence_messages_after_reset: 0
  staged_approach_status: FAILED
  staged_approach_error: fresh MuJoCo evidence timeout
diagnosis:
  - ResetWorld restored task_start in MuJoCo and RViz and the controller state stream continued, so physics, ros2_control, and GUI remained alive.
  - The evidence plugin's on_reset increments a pending generation; ordinary update intentionally refuses to consume it, but the fork reset callback returned without issuing the required paused on_state_snapshot hook.
  - Consequently the publisher endpoint remained discoverable while no atomic sample could be published, and staged_approach correctly failed closed before any arm motion.
  - The friction mapping was not physically exercised in this run; no approach, close, preload, or lift command was sent.
evidence:
  staged_result: /tmp/so101-task13-friction-parity/exp083-staged-approach.json
  staged_result_sha256: 37946d4ab06859393fbef47cac55daf4086b13c7198352bba45522b9dfe105aa
  after_reset_cua: /tmp/so101-task13-friction-parity/after-reset-cua.png
  after_reset_cua_sha256: 244b6bb688d3e367fd6bc06add0df16f9591a605a46a315e6902b3faa7b483ea
decision: KEEP VALID as a ResetWorld integration failure. Stop the friction replay and requalify ResetWorld evidence publication before any further grasp action.
```

## Checkpoint CP-118

```yaml
checkpoint_id: CP-118
checkpoint_time: 2026-08-12T02:12:20+08:00
last_valid_experiment: EXP-083
current_hypothesis: The missing post-reset paused snapshot hook is both necessary and sufficient to resume atomic evidence at the new reset epoch.
working_tree_status: Main worktree retains the intentional Task 13/14, friction-model, test, plan, and ledger changes at parent HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty. The independent fork submodule at 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5 has exactly two intentional dirty paths for the reset hook and regression test.
confirmed_conclusions:
  - GUI reset success alone is insufficient; a successful ResetWorld acceptance must also prove a fresh atomic sample at the incremented reset epoch.
  - A new fork regression test first failed because reset called on_reset but not on_state_snapshot, then passed after adding the paused snapshot hook under the same simulator mutex.
  - Fork package CTest passes all 4 registered tests after the fix.
disproven_routes:
  - Waiting for ordinary running updates cannot recover a pending reset generation by design and must not be used as a workaround.
open_risks:
  - The new hook must be revalidated twice in one live GUI stack and visually after a changed arm state before the grasp workflow resumes.
next_command: Start the GUI stack from /tmp/so101-fork-reset-test/install, preregister EXP-084, execute a bounded safe pose, then perform the formal ResetWorld transaction and verify fresh epoch evidence plus CUA task_start state.
```

## Experiment EXP-084

```yaml
experiment_id: EXP-084
prior_experiment: EXP-083 VALID reset-evidence publication failure
status: RUNNING
lifecycle: FIXED_FORK_RESET_EVIDENCE_AND_VISUAL_REQUALIFICATION
run_mode: two_same_stack_resets_with_changed_state_visual_proof
hypothesis: The fork's post-reset paused snapshot hook restores a step-zero atomic sample at each incremented epoch while preserving the fail-closed reset transaction and visual state restoration.
single_variable: Fork reset callback adds plugin on_state_snapshot(mj_model_, mj_data_, true) immediately after reset_simulation_state; the scene, demo overlay, friction model, controllers, services, and reset transaction are unchanged from EXP-083.
frozen_inputs:
  fork_base_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  fixed_fork_install: /tmp/so101-fork-reset-test/install
  fixed_fork_source_sha256: aca60fca0b41c8aa6a5eba6db3574f86bdcb70da3955972c20e665d5b6db5736
  fixed_fork_test_sha256: 82b971122fc5973d5fa7f13f1cc346072af228949980f412714eeb2ed072a8e6
  demo_install: /tmp/so101-friction-20260812/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-reset-evidence-fix
  reset_keyframe: task_start
  safe_pose: task12_safe
  expected_reset_epochs: [1, 2]
preconditions:
  - Focused reset regression test and all four fork CTest registrations pass; fork and demo installed hashes match their sources.
  - The replacement GUI stack is owned by tmux so101-mujoco-gui and starts at reset epoch 0 with active controllers and a fresh evidence stream.
success_criteria:
  - First formal deactivate-pause-reset-resume-activate transaction succeeds and a fresh unpaused evidence sample reports reset_epoch 1.
  - A bounded task12_safe MoveIt execution creates a visually distinct arm state without moving the cup.
  - Second formal reset transaction succeeds; a paused step-zero/new-epoch sample and subsequent fresh unpaused sample report reset_epoch 2, joint feedback returns to task_start, and CUA visually confirms the horizontal open arm plus original cup/table/pedestal/target state.
  - No process restart occurs between the two resets; no object write, hidden constraint, adhesion, mocap, or teleport outside the authorized keyframe ResetWorld transaction is used.
failure_criteria: Any service failure, missing/wrong epoch sample, controller activation failure, evidence timeout, joint mismatch, or visual mismatch keeps ResetWorld unqualified and blocks grasp replay.
invalid_criteria: Different fork/demo hashes, process restart between resets, missing CUA capture, or unrecorded state mutation makes the experiment INVALID.
evidence_root: /tmp/so101-task13-reset-evidence-fix
runtime_start:
  time: 2026-08-12T02:14:19+08:00
  precondition_readback: Fork CTest passed 4/4; the reset regression passed after first failing on the old callback; the owned GUI stack executable resolved to /tmp/so101-fork-reset-test/install; controllers were active; fresh evidence reported session so101-task13-reset-evidence-fix, reset epoch 0, running physics, and task-start cup/table state.
decision: PENDING. Preconditions and replacement-stack provenance passed; this state transition occurs before the first fixed-fork ResetWorld command.
next_experiment: Re-preregister the friction-parity grasp replay only if EXP-084 is VALID.
```

## Experiment EXP-084 Terminal Result

```yaml
experiment_id: EXP-084
status: INVALID
terminal_result: IMPLEMENTATION_AND_VISUAL_PASS_WITH_CONTAMINATED_FROZEN_EPOCH_BASELINE
terminal_time: 2026-08-12T02:24:56+08:00
result:
  fixed_fork_runtime_hook: PASS
  reset_client_unit_tests: 20 passed
  final_two_cycle_live_test: PASS
  final_two_cycle_epochs: [[4, 5], [5, 6]]
  authoritative_reset_steps: [0, 0]
  invalid_keyframe_fail_closed_epoch: 6
  before_reset_visual: task12_safe arm pose with upright cup
  after_reset_visual: horizontal open task_start arm, upright original cup, table, pedestal, and red target ring
invalid_reason:
  - The frozen input expected_reset_epochs was [1, 2], but three failed test-harness iterations performed real ResetWorld calls before the corrected final run.
  - Those diagnostic resets were visible in the simulator log but occurred after EXP-084 entered RUNNING and changed the initial epoch, so the final successful 4 -> 5 -> 6 pair cannot satisfy the preregistered exact baseline.
  - No hidden object write, attachment, constraint, adhesion, mocap, or teleport was used; the invalidation is provenance-only, not a physical or implementation failure.
evidence:
  safe_pose_json: /tmp/so101-task13-reset-evidence-fix/safe-pose.json
  safe_pose_sha256: 015d0346c94d83f1d84971708b2dc57f67571bf8a8ee9c5b57f6e08ee0c4d3de
  reset_live_log: /tmp/so101-task13-reset-evidence-fix/reset-live-fixed.log
  reset_live_log_sha256: d9f8afa4fef1e56a357dbed1eebfe998a257ec12b9f47a7579dd7a93a956fa17
  before_reset_cua: /tmp/so101-task13-reset-evidence-fix/before-reset-cua.png
  before_reset_cua_sha256: b62413a0243b71a438f02d56c9a4b44c77e8fd33969039b5224d14a7a763ab60
  after_reset_cua: /tmp/so101-task13-reset-evidence-fix/after-reset-cua.png
  after_reset_cua_sha256: d523b190a302d508efb5bbe9c9f7210345aa709355eec9dcccc0e1f19aa3d45f
decision: Preserve as implementation evidence, but do not qualify ResetWorld from this run. Restart a fresh owned stack and repeat the fixed test without code changes.
```

## Checkpoint CP-119

```yaml
checkpoint_id: CP-119
checkpoint_time: 2026-08-12T02:24:56+08:00
last_terminal_experiment: EXP-084 INVALID
current_hypothesis: The fixed fork and fixed reset client will reproduce exact 0 -> 1 -> 2 reset receipts on a fresh stack.
working_tree_status: Main worktree retains the intentional Task 13/14, friction, reset-client, tests, plan, and ledger changes at parent HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty. The fork submodule retains exactly the reset hook and regression test.
confirmed_conclusions:
  - Fork reset callback now publishes the authoritative paused step-zero snapshot immediately after state restoration.
  - The client must capture that step-zero snapshot before its bounded resume/activate/fresh-joints/re-pause phase; the final paused frame may legitimately have a positive simulation step.
  - A late subscriber on an already-paused stack must request an idempotent pause snapshot rather than passively waiting for volatile evidence.
open_risks:
  - Clean-epoch reproducibility remains unqualified until a new process starts at epoch 0 and completes exactly two cycles without intermediate failures.
next_command: Preregister EXP-085, restart the owned GUI stack with unchanged fixed hashes, execute task12_safe, and run the already-passing live test once.
```

## Experiment EXP-085

```yaml
experiment_id: EXP-085
prior_experiment: EXP-084 INVALID contaminated epoch baseline
status: RUNNING
lifecycle: CLEAN_FIXED_FORK_RESET_EVIDENCE_AND_VISUAL_REQUALIFICATION
run_mode: fresh_stack_exact_two_cycle_reset_with_changed_state_visual_proof
hypothesis: On a fresh stack, the unchanged fixed fork and reset client produce exact 0 -> 1 -> 2 authoritative step-zero receipts and restore the visibly changed arm/cup scene.
single_variable: Process epoch baseline only; code, fork install, demo install, model, controllers, services, scene, and test command are frozen from the final passing EXP-084 attempt.
frozen_inputs:
  fork_base_commit: 17fd1eca8d605d4f7c801eb7b54f3209f86f7cd5
  fixed_fork_install: /tmp/so101-fork-reset-test/install
  fixed_fork_source_sha256: aca60fca0b41c8aa6a5eba6db3574f86bdcb70da3955972c20e665d5b6db5736
  fixed_fork_test_sha256: 82b971122fc5973d5fa7f13f1cc346072af228949980f412714eeb2ed072a8e6
  reset_client_sha256: d57e67deb28ca17a7a489396caed043c796a4557a701a366d58b0bbb6b8d04dc
  reset_unit_test_sha256: cb2c77314f1487fe05f765c5efbb60af1c65e34151a23606b5ecb71f1164696f
  reset_live_test_sha256: 9eaa910ae4694ddf04e28e79a2a6022b5a8fc5abd852b6a7023ae862c461efc1
  demo_install: /tmp/so101-friction-20260812/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-reset-clean
  reset_keyframe: task_start
  safe_pose: task12_safe
  expected_initial_reset_epoch: 0
  expected_receipts: [[0, 1], [1, 2]]
preconditions:
  - A replacement owned GUI process starts fresh with the exact frozen installs, active controllers, reset epoch 0, and the formal RViz Planning Scene.
  - The already-fixed unit and live test sources are unchanged; protected Gazebo tracked status remains empty.
success_criteria:
  - task12_safe executes through MoveIt and CUA confirms a visibly changed arm with the original upright cup.
  - One invocation of the live test yields exact receipts [[0,1],[1,2]], both authoritative reset frames at simulation_step 0, final paused task_start joints/cup, active controllers, and invalid-keyframe fail-closed at epoch 2.
  - A new CUA capture confirms RViz left, MuJoCo right, horizontal open task_start arm, upright original cup, table, pedestal, and red target ring.
failure_criteria: Any wrong initial/final epoch, service/evidence/controller/joint/object mismatch, test failure, or visual mismatch blocks grasp replay.
invalid_criteria: Any code/hash change, intermediate reset outside the one test invocation, process restart during the two cycles, hidden state mutation, or missing visual evidence makes the run INVALID.
evidence_root: /tmp/so101-task13-reset-clean
runtime_start:
  time: 2026-08-12T02:28:21+08:00
  precondition_readback: Fresh owned GUI processes started from the frozen fixed-fork and friction demo installs; atomic evidence reports session so101-task13-reset-clean, reset epoch 0, running physics, original cup/table contact, and all three controllers active. No reset has occurred.
decision: PENDING. Fresh-stack provenance and exact epoch-zero preconditions passed; this transition occurs before Planning Scene setup, safe-pose motion, or ResetWorld.
next_experiment: Re-preregister the friction-parity grasp replay only if EXP-085 is VALID.
```

## Experiment EXP-085 Terminal Result

```yaml
experiment_id: EXP-085
status: INVALID
terminal_result: RESET_TRANSACTION_PASSED_BUT_LIVE_TEST_ASSERTED_STALE_SERVICE_RETURN_JOINT_SAMPLE
terminal_time: 2026-08-12T02:31:05+08:00
result:
  scene_setup: PASS with table, pedestal, and 13-primitive cup
  task12_safe_moveit_execution: PASS
  before_reset_visual: PASS
  actual_reset_receipts: [[0, 1], [1, 2]]
  authoritative_reset_steps: [0, 0]
  final_fresh_joint_convergence: PASS within 0.002 rad
  final_controllers_active: true
  test_result: FAILED in post-transaction diagnostic assertion
invalid_reason:
  - The test recorded /joint_states immediately when reset_world returned and required that asynchronous sample to already equal task_start.
  - ResetWorld atomically restores MuJoCo state and publishes step-zero evidence, but joint_state_broadcaster updates independently after the bounded resume/reactivate phase; the reset client correctly waits for a post-reset callback and final convergence.
  - The incorrect assertion failed only when the pre-reset arm was deliberately moved to task12_safe; earlier task_start-to-task_start runs hid the stale-sample error.
evidence:
  safe_pose_json: /tmp/so101-task13-reset-clean/safe-pose.json
  safe_pose_sha256: c6248cb10ab1b9f4eacb4624f7909824ed7dd6fab3461e1c07f2e7325218c2d5
  before_reset_cua: /tmp/so101-task13-reset-clean/before-reset-cua.png
  before_reset_cua_sha256: 3c35fb613596356afabc0ca25756a011c3bfd7fb82802f911f0d3c5ef2aa588e
  reset_live_log: /tmp/so101-task13-reset-clean/reset-live.log
  reset_live_log_sha256: 256605f24a2e6338883820f7f5f4b5b68d15c952ca536fb4b2c0629a1f06b108
decision: Correct the test terminology and gate placement, restart a fresh process, and rerun without changing runtime code.
```

## Checkpoint CP-120

```yaml
checkpoint_id: CP-120
checkpoint_time: 2026-08-12T02:31:05+08:00
last_terminal_experiment: EXP-085 INVALID
current_hypothesis: Service-return step-zero atomic state and post-reactivation fresh joint state are separate evidence boundaries and will both pass when checked at their correct times.
working_tree_status: Same intentional parent/fork dirty sets; protected Gazebo tracked status remains empty. Only the live-test assertion/field name changed after EXP-085.
confirmed_conclusions:
  - A changed task12_safe arm makes stale service-return joint feedback observable and prevents a false task_start-to-task_start pass.
  - Exact runtime receipts were 0 -> 1 -> 2 and both reset events had simulation_step 0; final fresh joints and controllers converged.
  - The live test must retain immediate atomic object/epoch/step checks but treat service-return joint data as diagnostic until a fresh callback arrives.
next_command: Preregister EXP-086 with the corrected test hash, restart the unchanged fixed runtime, and run the same scene/safe-pose/CUA/test sequence once.
```

## Experiment EXP-086

```yaml
experiment_id: EXP-086
prior_experiment: EXP-085 INVALID misplaced asynchronous joint assertion
status: RUNNING
lifecycle: FINAL_CLEAN_FIXED_FORK_RESET_REQUALIFICATION
run_mode: fresh_stack_exact_two_cycle_reset_with_correct_evidence_boundaries
hypothesis: With the test checking atomic reset state at service return and fresh joints after controller reactivation, the unchanged runtime passes exact 0 -> 1 -> 2 reset qualification and visual restoration.
single_variable: Live-test assertion timing/field semantics only; runtime fork, reset client, model, controller, scene, and motion inputs are unchanged.
frozen_inputs:
  fixed_fork_install: /tmp/so101-fork-reset-test/install
  fixed_fork_source_sha256: aca60fca0b41c8aa6a5eba6db3574f86bdcb70da3955972c20e665d5b6db5736
  fixed_fork_test_sha256: 82b971122fc5973d5fa7f13f1cc346072af228949980f412714eeb2ed072a8e6
  reset_client_sha256: d57e67deb28ca17a7a489396caed043c796a4557a701a366d58b0bbb6b8d04dc
  reset_unit_test_sha256: cb2c77314f1487fe05f765c5efbb60af1c65e34151a23606b5ecb71f1164696f
  corrected_reset_live_test_sha256: 875841af795e6e05517608f352f935d820b3cf052b663dea20b093988183946f
  demo_install: /tmp/so101-friction-20260812/overlay/install
  ros_domain_id: 149
  simulation_session_id: so101-task13-reset-final
  expected_initial_reset_epoch: 0
  expected_receipts: [[0, 1], [1, 2]]
preconditions:
  - A replacement owned GUI stack starts from the frozen installs at reset epoch 0 with active controllers and the formal Planning Scene.
  - task12_safe and a fresh CUA capture establish the changed-state visual baseline before the sole live-test invocation.
success_criteria:
  - The test exits 0 with exact receipts [[0,1],[1,2]], authoritative reset frames at step 0, final fresh task_start joints, active controllers, and invalid-keyframe fail-closed at epoch 2.
  - CUA after the test confirms the horizontal open task_start arm, original upright cup, table, pedestal, and red target ring in side-by-side RViz/MuJoCo.
failure_criteria: Any nonzero test result, wrong epoch, evidence/controller/joint/object mismatch, or visual mismatch blocks grasp replay.
invalid_criteria: Any further code change, reset outside the sole test invocation, process restart during the run, hidden state mutation, or missing CUA evidence invalidates the run.
evidence_root: /tmp/so101-task13-reset-final
runtime_start:
  time: 2026-08-12T02:33:02+08:00
  precondition_readback: Fresh owned GUI processes report the frozen session so101-task13-reset-final, reset epoch 0, running physics, original cup/table state, and all controllers active; corrected live-test hash matches the preregistered input and no reset has occurred.
decision: PENDING. Exact fresh-stack preconditions passed; this transition occurs before scene mutation, safe-pose motion, or ResetWorld.
next_experiment: Friction-parity grasp replay only after EXP-086 is VALID.
```

## Experiment EXP-086 Terminal Result

```yaml
experiment_id: EXP-086
status: VALID
terminal_result: CLEAN_RESETWORLD_TRANSACTION_AND_VISUAL_QUALIFICATION_PASS
terminal_time: 2026-08-12T02:35:44+08:00
commands:
  - command: ros2 run so101_mujoco_demo_py scene_setup
    exit_code: 0
  - command: ros2 run so101_mujoco_demo_py headless_execution --run-mode execute --execute --simulation-session-id so101-task13-reset-final --safe-pose task12_safe ...
    exit_code: 0
  - command: SO101_MUJOCO_RESET_LIVE_TEST=1 SO101_MUJOCO_SESSION_ID=so101-task13-reset-final python3 -m pytest -q -s test/test_reset_live_contract.py
    exit_code: 0
result:
  scene_setup: PASS with table, pedestal, and 13-primitive cup
  changed_state_moveit_execution: PASS, 19 points, simulation step delta 180
  before_reset_cua: PASS
  reset_receipts: [[0, 1], [1, 2]]
  authoritative_reset_steps: [0, 0]
  final_reset_epoch: 2
  final_paused_simulation_step: 1
  final_joint_positions: [6.874429849945374e-09, 0.0004841780340401403, 0.0004202376186071116, 5.106316234935229e-05, 2.8564715073084785e-08, -6.594769917410586e-07]
  final_object_position: [0.01999999708148165, -0.27999999885196103, 0.16494511319038987]
  controllers_active_before_invalid_keyframe: true
  invalid_keyframe_fail_closed: true at epoch 2 paused with arm/gripper controllers left inactive
  after_reset_cua: PASS with horizontal open task-start arm, original upright cup, table, pedestal, target ring, and visible PAUSE status
evidence:
  scene_safe_log: /tmp/so101-task13-reset-final/scene-safe.log
  scene_safe_log_sha256: 3d4143e51f72aac80804e62a7f8a6c5853788fb9b7818cf38c34b578d455c79b
  safe_pose_json: /tmp/so101-task13-reset-final/safe-pose.json
  safe_pose_sha256: a60ef83a79daaa6f8b086fc0d6bc028ac873a1e7b132a5bf5fbfc56e2d2cffd8
  before_reset_cua: /tmp/so101-task13-reset-final/before-reset-cua.png
  before_reset_cua_sha256: c23e39f50594786b4317be3605a8660d9c9ecdd558b382e57108a41d1a8fc71b
  reset_live_log: /tmp/so101-task13-reset-final/reset-live.log
  reset_live_log_sha256: d3fed3ad35b5985079df1f6de80e63afa03857d6e811df6b53bcdff425afa480
  after_reset_cua: /tmp/so101-task13-reset-final/after-reset-cua.png
  after_reset_cua_sha256: c12794bc0504c572794c0b4c280af3d542c992975505b82ed60418255dfc37ad
decision: QUALIFY ResetWorld. The grasp workflow may resume only in a separately preregistered experiment using the qualified fork/client behavior.
```

## Checkpoint CP-121

```yaml
checkpoint_id: CP-121
checkpoint_time: 2026-08-12T02:35:44+08:00
last_valid_experiment: EXP-086
current_hypothesis: The friction-parity mapping will preserve the qualified physical micro-lift for the preregistered 10-second hold.
working_tree_status: Main worktree retains intentional Task 13/14, friction, ResetWorld, tests, plan, and ledger changes at parent HEAD eabe88885bf802fb14968547634fd06c26c1b38a; protected Gazebo tracked status remains empty. Fork contains the now-live-qualified reset hook and regression.
confirmed_conclusions:
  - ResetWorld now has three independently verified boundaries: paused step-zero atomic MuJoCo evidence, post-reactivation fresh ROS joint/controller convergence, and CUA visual restoration.
  - A final paused frame may have simulation_step greater than zero because the transaction intentionally resumes for one or more control cycles; the receipt remains correlated to the captured step-zero frame.
  - The invalid-keyframe path leaves the simulator paused, leaves command controllers safely inactive, and does not advance reset epoch.
open_risks:
  - The friction mapping has not yet completed the exact 10-second physical hold replay after ResetWorld qualification.
next_command: Commit/push the independent fork reset fix, then preregister and execute the exact friction-parity approach/preload/micro-lift/10-second-hold replay on the qualified runtime.
```

## Experiment EXP-087

```yaml
experiment_id: EXP-087
prior_experiment: EXP-086 VALID clean ResetWorld qualification
status: RUNNING
lifecycle: FRICTION_PARITY_EXACT_GRASP_REPLAY_AND_10S_HOLD
run_mode: execute_staged_approach_then_exact_preload_micro_lift_sequence
hypothesis: Applying the Gazebo light-cup friction contract to MuJoCo prevents the prior slow cup slip while the unchanged bounded preload and micro-lift sequence remains within force and geometry limits.
prediction: After the same close, two 0.006 rad seating increments, two 2 mm arm increments, and one 3 mm arm increment, the cup remains 1.5-3.5 mm above its pre-lift height with bilateral fingertip contact, no table contact, at most 1 mm lateral drift, and force at or below 11.60 N for 10.0 continuous seconds.
single_variable: Friction mapping relative to EXP-077 through EXP-081 only: cup sliding friction 0.7 -> 1.2 and 13 fingertip-pad collisions sliding friction -> 3.0. Mass, inertias, geometry, controller, q6 bounds, approach, preload, arm targets, timestep, gravity, and no-attachment policy are unchanged.
frozen_inputs:
  parent_head: eabe88885bf802fb14968547634fd06c26c1b38a
  fork_commit: 20c77cd71305556cb5c914b07e8d5a4d40d5f3fd
  fork_remote: git@gitee.com:zjumty/mujoco_ros2_control.git
  runtime_fork_install: /tmp/so101-fork-reset-test/install
  demo_install: /tmp/so101-friction-20260812/overlay/install
  robot_mjcf_sha256: 846b460b4933924a64e3eec6ac3dc7a0f9d0f56baf73389e58ffaf6bcef79430
  scene_mjcf_sha256: aa830e733f9c9715c2e20dc148c70102f00a340e3218bf587fb150360d1b7ef5
  motion_policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
  ros_domain_id: 149
  simulation_session_id: so101-task13-reset-final
  expected_reset_epoch: 2
  replay_scripts:
    - [/tmp/so101_exp087_077_seating_preload.py, 8b766fe4f13f187f03f65cc85b904adfb23cfb9eaf4d80aa072d98d3d72f8d3a]
    - [/tmp/so101_exp087_078_micro_lift.py, c3c07e2289dacd718908fd9e49acd1348e1fcf20a3bd1f809ddeb4b25a6031a1]
    - [/tmp/so101_exp087_079_additional_preload.py, d9b32b35a816422679b7c23faa434b83e14c81214ea4c557cf168ec83f2dd60d]
    - [/tmp/so101_exp087_080_incremental_micro_lift.py, f351f000d122d3611f9d9b6b551c75fbc5204bd0f2fd29c6a85a6036592e3e28]
    - [/tmp/so101_exp087_081_incremental_3mm_lift.py, b91ba61481cdd9159a8c147147c96af92e2df73ab9e7206398d96a4e0b1a496d]
  maximum_force_n: 11.60
  long_hold_duration_s: 10.0
  minimum_physical_lift_m: 0.0015
  maximum_physical_lift_m: 0.0035
  maximum_lateral_drift_m: 0.001
preconditions:
  - EXP-086 left the same owned stack paused at epoch 2 in visually confirmed task_start state; the invalid-keyframe check intentionally left arm/gripper controllers inactive and they must be reactivated only after physics resumes.
  - The independent fork reset fix is committed and pushed as 20c77cd; protected Gazebo tracked status is empty.
  - Script hashes match, patched session/epoch/path fields are the only replay-script differences from the EXP-083 frozen scripts, and the friction overlay hashes match sources.
success_criteria:
  - Resume plus arm/gripper controller activation succeeds, formal scene_setup readback contains table, pedestal, and 13-primitive plastic_cup, and staged_approach reaches CLOSE_READY without early cup/fingertip contact or cup displacement.
  - All five replay scripts exit 0 in order without reset/session/pause change, force violation, loss of required bilateral contact, early table-support violation, or command failure.
  - The final script proves 1.5-3.5 mm physical cup lift, at most 1 mm lateral drift, no table contact, continuous bilateral contact for 10 seconds, and maximum force at or below 11.60 N.
failure_criteria: Any precondition, approach, controller, contact, force, lift, drift, table-contact, epoch, evidence, or long-hold violation stops before transport and is recorded VALID failure evidence.
invalid_criteria: Any unrecorded code/model/policy/preload/trajectory change, missing evidence, hidden constraint/weld/adhesion/mocap, object qpos/qvel write, teleport, or MuJoCo attachment makes the run INVALID.
evidence_root: /tmp/so101-task13-reset-final
runtime_start:
  time: 2026-08-12T02:40:01+08:00
  precondition_readback: The same owned process still resolves to /tmp/so101-fork-reset-test/install, EXP-086 ended paused at epoch 2 in visually confirmed task_start, arm/gripper controllers are safely inactive after the invalid-keyframe check, joint_state_broadcaster is active, source/install MJCF hashes and all five replay hashes match, fork 20c77cd is pushed, and protected Gazebo tracked status is empty.
decision: PENDING. Frozen provenance passed; this transition occurs before resume, controller activation, Planning Scene mutation, approach, close, preload, or lift.
next_experiment: Formal policy LIFT/transport only if EXP-087 is VALID 10-second hold success.
```

## Experiment EXP-087 Terminal Result

```yaml
experiment_id: EXP-087
status: VALID
terminal_result: FIRST_PRELOAD_SUCCEEDED_FIRST_2MM_PHYSICAL_LIFT_FAILED
terminal_time: 2026-08-12T02:43:21+08:00
commands:
  - command: resume plus activate arm_controller and gripper_controller
    exit_code: 0
  - command: scene_setup plus staged_approach through DESCEND
    exit_code: 0
  - command: python3 /tmp/so101_exp087_077_seating_preload.py
    exit_code: 0
  - command: python3 /tmp/so101_exp087_078_micro_lift.py
    exit_code: 1
  - command: remaining EXP-079/080/081 replay scripts
    exit_code: NOT_RUN
result:
  staged_approach_status: CLOSE_READY
  first_preload_status: PASS
  first_preload_q6_rad: -0.053606676358756614
  first_preload_cup_displacement_m: 0.0012796828421551443
  first_2mm_plan_to_execute_drift_rad: 8.297002973556289e-09
  first_2mm_controller_result: Controller and MoveIt logs report goal reached and SUCCEEDED
  first_2mm_script_result: MOVEIT_EXECUTION_MONITOR_ABORTED
  terminal_arm_joints_rad: [-0.00013512141868308767, 0.4632203191966657, 0.21299495268873445, 0.8648784483336789, 0.0006288526583899354]
  terminal_q6_rad: -0.05360712557467238
  terminal_cup_position_m: [0.020001111170286065, -0.2790017238509583, 0.16471177966890116]
  terminal_table_contact: true
  terminal_bilateral_contacts: [3, 4]
  terminal_maximum_force_n: 0.19609305915459255
diagnosis:
  - The arm trajectory itself completed, but the execution monitor observed a transient loss of the required bilateral-contact invariant and cancelled its owned MoveIt action before accepting the result response.
  - The final arm joint state is at the intended first 2 mm increment, while the cup remains table-supported at its original height; therefore the physical lift gate failed regardless of the action-result race.
  - This matches the prior sequence's reason for introducing one separately bounded additional 0.006 rad preload before the second 2 mm attempt; no remaining script was run automatically.
evidence:
  approach_log_sha256: fdf7316d6f0859685f0786f529a6d929f7e726657501afcf4b4b3ab02e9f7c44
  staged_approach_sha256: 1f8331d05320dd9fe21fa75d8053e8c72b58deb1b748950fb42bca19492a11c4
  replay_log_sha256: 66f406294c8f395066ac644182ba71436f7bdbbcc47f2875936e568aba449d9a
  first_preload_sha256: 28f4098867876bc442e318e2acb6b3638810047b5b8e44be6517ed1197ccce24
  first_2mm_sha256: 2ebfc58fb275cb5c59ce08ddd599a880b8e847f9165fcdeb470aec5cfbb35d24
  terminal_atomic_evidence_sha256: 93125c470aaaaaf3dcb27d2b245c0499954dc63835a677a536e4e37f2b6ead41
decision: Keep as a physical failure, preserve the unchanged live state, and preregister the already-designed additional preload plus remaining lift sequence separately.
```

## Checkpoint CP-122

```yaml
checkpoint_id: CP-122
checkpoint_time: 2026-08-12T02:43:21+08:00
last_valid_experiment: EXP-087
current_hypothesis: The second 0.006 rad q6 seating increment raises pad normal force enough for the exact remaining lift sequence.
working_tree_status: Same intentional parent dirty set plus committed/pushed fork gitlink at 20c77cd; protected Gazebo tracked status remains empty. Same owned stack runs at epoch 2 without pause/reset/session change.
confirmed_conclusions:
  - Friction parity alone does not make the first single-preload 2 mm increment carry the cup.
  - The first 2 mm arm target was reached with negligible handoff drift, but the cup stayed on the table, so this is a physical grasp-load failure rather than a planner failure.
open_risks:
  - The remaining q6 preload margin is bounded and must not be extended beyond the pre-existing second 0.006 rad increment without a new safety review.
next_command: Preregister EXP-088 from the current live state, run the exact additional-preload script, then the second 2 mm and final 3 mm scripts only while all gates remain satisfied.
```

## Experiment EXP-088

```yaml
experiment_id: EXP-088
prior_experiment: EXP-087 VALID first 2 mm physical-lift failure
status: RUNNING
lifecycle: SECOND_PRELOAD_REMAINING_MICRO_LIFTS_AND_10S_HOLD
run_mode: continue_current_physical_state_with_exact_exp079_080_081_sequence
hypothesis: The frozen additional 0.006 rad q6 preload raises fingertip normal force sufficiently for the remaining second 2 mm and final 3 mm arm increments to lift and hold the cup under friction parity.
single_variable: Apply only the previously frozen second 0.006 rad q6 seating increment; all arm targets, friction, model, controller, physics, scene, session, and no-attachment policy remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-reset-final
  reset_epoch: 2
  initial_q6_rad: -0.05360712557467238
  initial_arm_joints_rad: [-0.00013512141868308767, 0.4632203191966657, 0.21299495268873445, 0.8648784483336789, 0.0006288526583899354]
  initial_cup_position_m: [0.020001111170286065, -0.2790017238509583, 0.16471177966890116]
  scripts:
    - [/tmp/so101_exp087_079_additional_preload.py, d9b32b35a816422679b7c23faa434b83e14c81214ea4c557cf168ec83f2dd60d]
    - [/tmp/so101_exp087_080_incremental_micro_lift.py, f351f000d122d3611f9d9b6b551c75fbc5204bd0f2fd29c6a85a6036592e3e28]
    - [/tmp/so101_exp087_081_incremental_3mm_lift.py, b91ba61481cdd9159a8c147147c96af92e2df73ab9e7206398d96a4e0b1a496d]
  maximum_force_n: 11.60
  final_hold_duration_s: 10.0
  final_lift_gate_m: [0.0015, 0.0035]
  maximum_lateral_drift_m: 0.001
preconditions:
  - Same process/session/epoch is running and unpaused; arm/gripper controllers are active; q6, arm, cup, table support, bilateral contact, and force match the EXP-087 terminal state within script tolerances.
  - No ResetWorld, scene/model change, object write, attachment, constraint, or unrecorded command occurred after EXP-087.
success_criteria:
  - Additional preload, second 2 mm lift, and final 3 mm lift scripts each exit 0 in order.
  - Final physical gate proves 1.5-3.5 mm cup lift relative to its own start, at most 1 mm lateral drift, no table contact, continuous bilateral contact for 10 seconds, force at or below 11.60 N, unchanged epoch/session, and no hidden aid.
failure_criteria: Any state mismatch, command failure, q6/force/contact/table/lift/drift/evidence violation stops before the next script and is recorded.
invalid_criteria: Any unrecorded mutation or missing evidence invalidates the run.
evidence_root: /tmp/so101-task13-reset-final
runtime_start:
  time: 2026-08-12T02:45:13+08:00
  precondition_readback: Fresh atomic evidence and joint feedback match the frozen session, epoch, table-supported cup, bilateral 3/4 contacts, arm target, q6, and force state; controllers and physics remain active/running, hashes match, and no intervening command occurred.
decision: PENDING. Exact continuation-state preconditions passed; this transition occurs before the additional preload or remaining lift commands.
next_experiment: Formal policy LIFT/transport only after a VALID 10-second hold success.
```

## Experiment EXP-088 Terminal Result

```yaml
experiment_id: EXP-088
status: VALID
terminal_result: ADDITIONAL_PRELOAD_SUCCEEDED_SECOND_2MM_PHYSICAL_LIFT_FAILED
terminal_time: 2026-08-12T02:45:29+08:00
commands:
  - command: python3 /tmp/so101_exp087_079_additional_preload.py
    exit_code: 0
  - command: python3 /tmp/so101_exp087_080_incremental_micro_lift.py
    exit_code: 1
  - command: final 3 mm script
    exit_code: NOT_RUN
result:
  additional_preload_status: ADDITIONAL_PRELOAD_PROVED
  q6_after_preload_rad: -0.05959697741793274
  preload_cup_displacement_m: 0.00022107967542450702
  second_2mm_physical_lift_m: 0.000011932501217309932
  terminal_arm_joints_rad: [-0.00012527913306650937, 0.4536258785278432, 0.2112317383032714, 0.8748803245910441, 0.0006535962555246532]
  terminal_q6_rad: -0.0595972283551498
  terminal_cup_position_m: [0.020007196171377813, -0.279033163746999, 0.16471177913701351]
  terminal_table_contact: true
  terminal_paused: false
  terminal_reset_epoch: 2
  terminal_maximum_force_n: 0.1963338982477806
diagnosis:
  - The final allowed q6 preload completed within the frozen bound and retained bilateral contact.
  - The second 2 mm arm target executed, but the cup rose only 0.0119 mm and remained table-supported, far below the 1.5 mm physical gate.
  - No extra preload is authorized; the only remaining frozen action is the prior sequence's final 3 mm increment, which previously produced a transient 2.097 mm lift.
evidence:
  additional_preload_log_sha256: 2a71b0125eb980a97d1e1fe74b5256b235c432a1dc874d2cc89076cd480ab0aa
  additional_preload_json_sha256: 2ba33895225b902b97cfbd196d2e2681abd18536a9eaf83d21c7894b7d125030
  second_2mm_log_sha256: 95a2f183a7a69dd6cc19d98e5e41660c30c760747e31ae07561f1ca3b679b81c
  second_2mm_json_sha256: 19dd43f020d3b3807b0713e340f72ddd036f430590e5e16b845dce13a98fce89
  terminal_joints_sha256: 0c57a0efd235ecd9209b008da628583aac283607ac03c305998c42b7cec5a184
  terminal_atomic_evidence_sha256: 493376e4413b1d9043861fe273e63cd461b5cc74498daa50ef9b21c3aaa9c47c
decision: Keep as a physical failure and preregister the unchanged final 3 mm increment plus 10-second hold from this exact state. Do not increase q6 preload.
```

## Checkpoint CP-123

```yaml
checkpoint_id: CP-123
checkpoint_time: 2026-08-12T02:45:29+08:00
last_valid_experiment: EXP-088
current_hypothesis: The final 3 mm increment supplies the remaining kinematic lift, and friction parity determines whether the resulting physical lift persists.
working_tree_status: Same intentional parent/fork state; same owned process/session/epoch runs unpaused with the final bounded preload and second 2 mm arm target.
confirmed_conclusions:
  - No further gripper preload is permitted by the frozen sequence or safety margin.
  - The two 2 mm increments did not carry the cup; transport remains blocked.
next_command: Preregister EXP-089 and run only the frozen final 3 mm script with its 10-second continuous bilateral/no-table/force/lift gate.
```

## Experiment EXP-089

```yaml
experiment_id: EXP-089
prior_experiment: EXP-088 VALID second 2 mm physical-lift failure
status: RUNNING
lifecycle: FINAL_3MM_PHYSICAL_LIFT_AND_10S_STABLE_HOLD
run_mode: continue_exact_current_state_with_only_frozen_final_increment
hypothesis: The final 3 mm arm increment reproduces the prior 2.097 mm cup lift, while the new cup/pad friction mapping prevents the prior long-hold slip.
single_variable: Execute only the frozen final 3 mm arm target from the exact EXP-088 terminal state; no q6, model, controller, scene, epoch, or policy change.
frozen_inputs:
  simulation_session_id: so101-task13-reset-final
  reset_epoch: 2
  initial_arm_joints_rad: [-0.00012527913306650937, 0.4536258785278432, 0.2112317383032714, 0.8748803245910441, 0.0006535962555246532]
  initial_q6_rad: -0.0595972283551498
  initial_cup_position_m: [0.020007196171377813, -0.279033163746999, 0.16471177913701351]
  script: [/tmp/so101_exp087_081_incremental_3mm_lift.py, b91ba61481cdd9159a8c147147c96af92e2df73ab9e7206398d96a4e0b1a496d]
  maximum_force_n: 11.60
  hold_duration_s: 10.0
  lift_gate_m: [0.0015, 0.0035]
  maximum_lateral_drift_m: 0.001
preconditions:
  - Same process/session/epoch is unpaused with active controllers, bilateral fingertip contact, table-supported cup, frozen arm/q6 state, and no intervening action.
  - Script and model hashes match; no hidden aid or object-state mutation exists.
success_criteria:
  - Script exits 0 and proves 1.5-3.5 mm lift, at most 1 mm lateral drift, no table contact, continuous bilateral contact for 10 seconds, force at or below 11.60 N, unchanged session/epoch, and no hidden aid.
failure_criteria: Any command/monitor/contact/table/lift/drift/force/evidence failure stops and blocks transport.
invalid_criteria: Any unrecorded state change or missing evidence invalidates the run.
evidence_root: /tmp/so101-task13-reset-final
runtime_start:
  time: 2026-08-12T02:46:50+08:00
  precondition_readback: Fresh joint and atomic evidence match the frozen arm, q6, cup/table, unpaused epoch-2 session and active-contact state; no intervening command, reset, pause, or mutation occurred and the final-script hash matches.
decision: PENDING. Exact continuation preconditions passed; this transition occurs before the sole final 3 mm command.
next_experiment: Formal policy LIFT/transport only after VALID success.
```

## Experiment EXP-089 Terminal Result

```yaml
experiment_id: EXP-089
status: VALID
terminal_result: FINAL_3MM_ARM_INCREMENT_SUCCEEDED_PHYSICAL_CUP_LIFT_FAILED
terminal_time: 2026-08-12T02:46:52+08:00
commands:
  - command: python3 /tmp/so101_exp087_081_incremental_3mm_lift.py
    exit_code: 1
result:
  controller_and_moveit_result: SUCCEEDED
  plan_to_execute_drift_rad: 3.3637154173149497e-10
  physical_cup_lift_m: -1.2062656151723417e-09
  terminal_arm_joints_rad: [-0.0003013723145362924, 0.4391831977848682, 0.20831482541019763, 0.889797311475596, 0.0005881521735593593]
  terminal_q6_rad: -0.05959721999962248
  terminal_cup_position_m: [0.020007094752016574, -0.2790331642119319, 0.16471177976905596]
  terminal_table_contact: true
  terminal_bilateral_contacts: [3, 4]
  terminal_maximum_normal_force_n: 0.19634095434620263
  terminal_reset_epoch: 2
  terminal_paused: false
diagnosis:
  - The frozen arm target planned and executed from the correct start state, so planner handoff and controller execution are not the limiting factor.
  - The cup remained table-supported with effectively zero vertical displacement despite bilateral pad contact at the final safe q6 lower bound.
  - The reported maximum normal force is dominated by the table carrying the approximately 0.196 N cup weight; the pad contacts remain too compliant to generate the required lateral squeeze force.
  - No further q6 preload is permitted. Friction-only parity is disproven; contact stiffness and damping parity must be introduced and calibrated as the next single model variable.
evidence:
  final_3mm_log_sha256: 39c693d33720b8a996da814528d0d774b6ee78f888ba533fbbb39517da6319e8
  final_3mm_json_sha256: 35007f941c2ca82f01ebaec897f8b0c48c8e10e0cfdc47c8a386bd04f0998488
  replay_script_sha256: b91ba61481cdd9159a8c147147c96af92e2df73ab9e7206398d96a4e0b1a496d
  post_failure_reset_cua_sha256: c237a0b2e7aaa0713c8332bbe1c7d554c8a448b2a505aba62ad3092ada2cb430
decision: Keep as a physical failure. Stop the unchanged friction-only route and return to task_start before any model-calibration experiment.
```

## Checkpoint CP-124

```yaml
checkpoint_id: CP-124
checkpoint_time: 2026-08-12T02:47:10+08:00
last_valid_experiment: EXP-089
current_hypothesis: The missing Gazebo-to-MuJoCo contact-stiffness mapping, rather than friction or arm trajectory, prevents the pads from developing enough normal squeeze force at the safe q6 limit.
working_tree_status: Same intentional parent/fork state and protected Gazebo tracked status remains empty. The current owned stack is still running at epoch 2 in the EXP-089 terminal pose and must be reset before the model changes take effect.
confirmed_conclusions:
  - All three bounded lift increments failed to carry the cup under friction-only parity; the final 3 mm increment produced effectively zero lift.
  - The gripper is already at its safe lower bound, so additional preload is both unauthorized and physically uninformative.
  - Gazebo's light plastic cup contract specifies 1000000 N/m contact stiffness and 100 N s/m contact damping, while the MuJoCo fingertip pad geoms currently specify friction only and inherit the default soft solver contact.
  - MuJoCo's documented direct solref format is (-stiffness, -damping); this supplies a formal, reviewable mapping for the missing material contract.
open_risks:
  - A direct 1000000/100 mapping may make the 2 ms simulation numerically stiff or exceed the 11.60 N force gate; the first run must be contact-only and fail closed before any lift.
next_command: Add a static parity test, map only the fingertip pad contact solver parameters, rebuild a new overlay, reset to task_start, and preregister EXP-090 as a bounded contact-only calibration before replaying any lift.
```

## Experiment EXP-090

```yaml
experiment_id: EXP-090
prior_experiment: EXP-089 VALID friction-only physical-lift failure
status: RUNNING
lifecycle: STIFF_TPU_CONTACT_ONLY_CALIBRATION
run_mode: fresh_stack_staged_approach_then_incremental_gripper_contact_search_without_lift
hypothesis: Mapping the Gazebo TPU contact stiffness and damping through MuJoCo direct-format solref will generate at least 0.05 N normal force on each fingertip side before q6 reaches its safe lower bound, while remaining below the 11.60 N diagnostic force limit.
single_variable: Add solref="-1000000 -100" to the same 13 fingertip pad collision geoms; friction, geometry, masses, actuators, controllers, motion policy, cup, scene, and no-attachment contract remain unchanged.
frozen_inputs:
  source_commit: eabe88885bf802fb14968547634fd06c26c1b38a
  dependency_commit: 20c77cd71305556cb5c914b07e8d5a4d40d5f3fd
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  motion_policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
  contact_script: [/tmp/so101_exp090_contact_only.py, dfa6e9f8fc14c38cc929b8b1ccfa353922b022dd95e754a85153acaef60727cd]
  maximum_force_n: 11.60
  minimum_per_side_normal_force_n: 0.05
  maximum_cup_displacement_m: 0.003
  stable_contact_hold_s: 2.0
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - Static RED proved the solver mapping was absent; the production mapping then made the complete visual-geometry parity test pass 9/9.
  - The new overlay built successfully and source/install robot MJCF hashes match exactly.
  - Both live robot_description publishers and the MuJoCo control-node log resolve the same new stiffness-overlay scene path; the control process resolves to the committed fork install.
  - The previous stack was reset to task_start and CUA confirmed the horizontal open-arm pose, upright cup, complete scene, split RViz/Viewer layout, and PAUSE before shutdown.
  - The fresh stiffness stack is unpaused at epoch 0 with active arm, gripper, and joint-state controllers; the cup is upright and table-supported without fingertip contact.
  - Formal scene_setup has published table, pedestal, and 13-primitive plastic_cup into the Planning Scene. No gripper, approach, contact, or lift action has occurred on the fresh stack.
success_criteria:
  - Staged approach reaches CLOSE_READY with the preopened gripper, no early fingertip contact, no forbidden contact, and at most 3 mm cup displacement.
  - Incremental q6 search reaches continuous bilateral contact with at least 0.05 N summed normal force on each side before the safe lower q6 bound.
  - The contact-only state remains bilateral and above the force threshold for 2 seconds, never exceeds 11.60 N diagnostic force, and never moves the cup more than 3 mm.
  - No lift/transport, pause, reset, attachment, simulator constraint, direct object write, or hidden aid occurs.
failure_criteria: Any provenance, approach, contact-shape, q6, force, cup-displacement, freshness, or hold violation stops before lift and is recorded.
invalid_criteria: Any unrecorded model/policy/script change, missing evidence, weld/equality/adhesion/mocap, teleport, object qpos/qvel write, or simulator attachment invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:03:10+08:00
  precondition_readback: Source and installed robot MJCF hash to f87a033f; both robot_description publishers point to the stiffness overlay; controllers are active; session so101-task13-stiffness is epoch 0 unpaused; the formal Planning Scene setup reports pedestal 1, plastic_cup 13, table 1.
decision: PENDING. This transition occurs before staged approach or any gripper/contact command.
next_experiment: Only a separately preregistered bounded micro-lift if contact-only calibration succeeds.
```

## Experiment EXP-090 Terminal Result

```yaml
experiment_id: EXP-090
status: INVALID
terminal_result: EXECUTE_GATE_OMITTED_FAIL_CLOSED_BEFORE_ACTION
terminal_time: 2026-08-12T03:04:30+08:00
command: ros2 run so101_mujoco_demo_py staged_approach --mode execute --stop-after DESCEND --simulation-session-id so101-task13-stiffness --evidence-file /tmp/so101-task13-stiffness/exp090-staged-approach.json --hold-seconds 0.30
exit_code: 1
result:
  error: RuntimeError execute mode requires the explicit --execute gate
  physical_action_started: false
  terminal_arm_joints_rad: [9.669045102590511e-10, 0.0007098293985419334, 0.0006050452792909555, 0.00013253723931816417, 1.6341604703459425e-07]
  terminal_q6_rad: -7.08100519845596e-06
  terminal_reset_epoch: 0
  terminal_paused: false
  terminal_fingertip_contacts: [0, 0]
  terminal_cup_position_m: [0.01999916533885187, -0.28000042380956286, 0.16471177879121365]
diagnosis:
  - The runtime intentionally requires both --mode execute and the explicit --execute acknowledgement; omitting the second gate is a harness invocation error.
  - The command failed before gripper preopen, planning, execution, or contact. Fresh joint and atomic evidence confirm the epoch-0 task_start physical baseline is unchanged.
evidence:
  staged_approach_log_sha256: df05cdaff81f357dd6e4269935528451b7e95532984c38dbd86bf81ec33658d6
decision: Do not count this as contact-model evidence. Preserve the unchanged stack and preregister a corrected invocation as a new experiment.
```

## Checkpoint CP-125

```yaml
checkpoint_id: CP-125
checkpoint_time: 2026-08-12T03:04:35+08:00
last_valid_experiment: EXP-089
last_invalid_experiment: EXP-090
current_hypothesis: Unchanged from CP-124; EXP-090 exercised only the staged-approach execution gate and supplied no physical contact evidence.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state. Protected Gazebo tracked status is empty. Fresh stiffness stack remains epoch 0 unpaused at task_start with formal Planning Scene loaded.
confirmed_conclusions:
  - The staged-approach CLI fails closed if --execute is absent even when mode is execute.
  - No robot, cup, session, epoch, or model state changed during the invalid invocation.
next_command: Preregister EXP-091 with the same frozen inputs and the corrected explicit --execute flag, then run staged approach followed by the unchanged contact-only script if and only if CLOSE_READY succeeds.
```

## Experiment EXP-091

```yaml
experiment_id: EXP-091
prior_experiment: EXP-090 INVALID pre-action invocation error
status: RUNNING
lifecycle: STIFF_TPU_CONTACT_ONLY_CALIBRATION_RETRY
run_mode: unchanged_fresh_stack_with_corrected_staged_approach_execute_gate
hypothesis: Same as EXP-090: the direct stiffness/damping mapping yields at least 0.05 N normal force per fingertip side within the safe q6 bound and below 11.60 N.
single_variable: Relative to the invalid EXP-090 harness invocation, add only the required --execute acknowledgement; model, scene, session, epoch, policy, script, bounds, and physical baseline are unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  motion_policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
  contact_script: [/tmp/so101_exp090_contact_only.py, dfa6e9f8fc14c38cc929b8b1ccfa353922b022dd95e754a85153acaef60727cd]
  maximum_force_n: 11.60
  minimum_per_side_normal_force_n: 0.05
  maximum_cup_displacement_m: 0.003
  stable_contact_hold_s: 2.0
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - All EXP-090 provenance and safety preconditions remain true.
  - Fresh post-failure joint and atomic evidence proves task_start, epoch 0, unpaused physics, zero fingertip contact, and unchanged upright table-supported cup.
success_criteria:
  - Corrected staged approach reaches CLOSE_READY under all pre-contact gates.
  - The frozen contact-only script proves the same bilateral force, q6, displacement, force ceiling, duration, provenance, and no-hidden-aid gates from EXP-090.
failure_criteria: Any approach or contact-only gate violation stops before lift.
invalid_criteria: Any state/model/policy/script mutation beyond the explicit --execute correction invalidates the retry.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:04:40+08:00
  precondition_readback: EXP-090 failed before action; current joints remain approximately task_start, session/epoch remain so101-task13-stiffness/0, physics is unpaused, and the cup remains table-supported with no fingertip contact.
decision: PENDING. This transition occurs before the corrected staged-approach command.
next_experiment: Separately preregister micro-lift only after VALID contact-only success.
```

## Experiment EXP-091 Terminal Result

```yaml
experiment_id: EXP-091
status: VALID
terminal_result: STAGED_APPROACH_SUCCEEDED_FIRST_CONTACT_SEARCH_WAS_TRANSIENT_RIGHT_ONLY
terminal_time: 2026-08-12T03:06:25+08:00
commands:
  - command: staged_approach --mode execute --execute --stop-after DESCEND
    exit_code: 0
  - command: python3 /tmp/so101_exp090_contact_only.py
    exit_code: 1
result:
  staged_approach_status: CLOSE_READY
  staged_approach_segments: 15
  q6_command_rad: -0.040
  sampled_actual_q6_rad: -0.038771091495019894
  transient_left_contact_count: 0
  transient_right_contact_count: 2
  transient_right_normal_force_sum_n: 0.41460596890672896
  transient_maximum_normal_force_n: 0.303588638561013
  terminal_q6_rad: -0.03999977306884794
  terminal_fingertip_contacts: [0, 0]
  terminal_cup_position_m: [0.01999885918621051, -0.2793983281444021, 0.1647117783475176]
  cup_displacement_from_exp091_start_m: 0.000602230484
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The corrected staged approach completed all 15 selected waypoints with no early contact and reached the verified CLOSE_READY arm state.
  - The first bounded gripper command produced a transient right-pad contact well below the force ceiling, shifting the free cup approximately 0.60 mm toward the fixed finger, then settled at q6=-0.04 with no fingertip contact.
  - Treating any contact before the nominal search bound as a script error was too strict: one-sided contact is the expected seating mechanism needed to move the free cup into bilateral alignment.
evidence:
  staged_approach_log_sha256: 500ff9c9853009e77e83cfabea882dd9c9d59f0061eeac3f1656fc106bd425e2
  staged_approach_json_sha256: 0ae8b5271fa7227f1e2839621f148819a3a7aae3bc75917fa5a252de8d6926cb
  contact_log_sha256: a6c8533947709bc68d0e5bf0894de1bacacc6eaa98d87d481bc68c777745c8a4
  contact_json_sha256: 8c563404de36c3ae57b86cdcecdabadbebef03823b38ed43804c069c3eb8b723
decision: Preserve the exact live state. Do not rerun the arm approach; preregister a continuation that permits bounded unilateral seating while retaining all q6, force, displacement, provenance, and no-hidden-aid gates.
```

## Checkpoint CP-126

```yaml
checkpoint_id: CP-126
checkpoint_time: 2026-08-12T03:06:30+08:00
last_valid_experiment: EXP-091
current_hypothesis: Continued incremental closing from q6=-0.04 will seat the cup against the fixed finger and produce bounded bilateral contact before the safe q6 lower limit.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status is empty. Same stiffness process/session/epoch remains unpaused at CLOSE_READY.
confirmed_conclusions:
  - Direct stiffness/damping mapping changes pad contact from the prior near-zero squeeze response to a measurable, safe unilateral force.
  - The first contact was transient because the cup moved laterally on the table; this is seating behavior, not force instability.
  - Total cup displacement remains below the frozen 3 mm limit and the next action can continue from the exact state without resetting or replanning the arm.
next_command: Preregister EXP-092 and continue q6 in bounded coarse steps until bilateral contact, switching to 20 microradian steps once bilateral contact appears; stop on every existing force, displacement, q6, freshness, or provenance gate.
```

## Experiment EXP-092

```yaml
experiment_id: EXP-092
prior_experiment: EXP-091 VALID transient unilateral seating contact
status: RUNNING
lifecycle: STIFF_TPU_BILATERAL_CONTACT_CONTINUATION
run_mode: continue_exact_close_ready_state_without_arm_motion_or_reset
hypothesis: Bounded q6 continuation seats the free cup against the fixed finger and yields at least 0.05 N summed normal force per side for 2 seconds below all safety gates.
single_variable: Relative to EXP-091, permit transient unilateral seating contact instead of failing immediately; model, policy, state, q6 steps, bounds, session, and no-attachment contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_q6_rad: -0.03999977306884794
  initial_cup_position_m: [0.01999885918621051, -0.2793983281444021, 0.1647117783475176]
  reference_cup_position_m: [0.019998946077560063, -0.2800005586174245, 0.16471177790961924]
  contact_script: [/tmp/so101_exp092_contact_only.py, f56aeea3aed1ef6137371f8954e8300698b0c09c31536f0e9ea1bc5403781f98]
  coarse_q6_step_rad: 0.0005
  post_bilateral_q6_step_rad: 0.00002
  maximum_force_n: 11.60
  minimum_per_side_normal_force_n: 0.05
  maximum_total_cup_displacement_m: 0.003
  stable_contact_hold_s: 2.0
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - Same live process/session/epoch remains unpaused; controllers are active and the arm remains within 0.01 rad of CLOSE_READY.
  - Fresh joint and atomic evidence match q6=-0.04, zero terminal fingertip contacts, 0.60 mm total cup seating displacement, table support, and force below the ceiling.
  - Script hash matches; no reset, pause, model/policy change, arm motion, object write, or hidden aid occurred after EXP-091.
success_criteria:
  - Bilateral contact reaches at least 0.05 N summed normal force on both sides before the q6 lower bound.
  - That condition holds continuously for 2 seconds with force at or below 11.60 N and total cup displacement at or below 3 mm.
  - Session/epoch remain unchanged and no lift, arm motion, simulator constraint, attachment, pause, or direct object write occurs.
failure_criteria: Any force, displacement, q6, bilateral-hold, freshness, session, epoch, controller, or action failure stops before lift.
invalid_criteria: Any unrecorded state/script/model/policy change or hidden physical aid invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:07:20+08:00
  precondition_readback: Fresh state matches CP-126 and the continuation script is lint-clean with SHA f56aeea3; this transition occurs before the first continuation q6 command.
decision: PENDING.
next_experiment: Separately preregister one bounded 2 mm physical micro-lift only after VALID bilateral contact-only success.
```

## Experiment EXP-092 Terminal Result

```yaml
experiment_id: EXP-092
status: VALID
terminal_result: BILATERAL_CONTACT_ONLY_PROVED
terminal_time: 2026-08-12T03:08:41+08:00
command: python3 /tmp/so101_exp092_contact_only.py
exit_code: 0
result:
  terminal_q6_rad: -0.04740743964538249
  hold_duration_s: 2.0
  hold_sample_count: 168
  left_normal_force_range_n: [0.1674629373468175, 0.17051632337500633]
  right_normal_force_range_n: [0.16746052286713659, 0.17015631805109943]
  maximum_normal_force_n: 0.19634463904274616
  terminal_contact_counts: [1, 1]
  terminal_cup_position_m: [0.019998915139546485, -0.2789645715010863, 0.16471177965894526]
  total_cup_displacement_m: 0.001035987118
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The bounded seating continuation brought the cup into symmetric one-contact-per-side support without approaching the q6 lower bound.
  - Each side sustained more than three times the preregistered 0.05 N normal-force threshold for the full 2-second window, while the global maximum stayed near the table's 0.196 N cup-weight reaction and far below 11.60 N.
  - With MuJoCo sliding friction 3.0, the measured bilateral normal force supplies a theoretical friction margin above the 0.196 N cup weight; a physical lift is now separately testable.
evidence:
  contact_log_sha256: ece17372fd06e67c9e8ee26e76da224402bdeb822aba921326850fea67d1f429
  contact_json_sha256: 16b56138b69a846fcd00ae43b87c083f59568b002d58a705700ffe720247a615
  contact_script_sha256: f56aeea3aed1ef6137371f8954e8300698b0c09c31536f0e9ea1bc5403781f98
decision: Preserve the exact bilateral live state and preregister one 2 mm arm micro-lift without changing q6 or any model/policy parameter.
```

## Checkpoint CP-127

```yaml
checkpoint_id: CP-127
checkpoint_time: 2026-08-12T03:08:45+08:00
last_valid_experiment: EXP-092
current_hypothesis: The proven bilateral pad normal force will carry the cup through the unchanged 2 mm arm increment while retaining bilateral contact and clearing table support.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status remains empty. Same stiffness process/session/epoch remains unpaused at CLOSE_READY with q6 held at -0.04741.
confirmed_conclusions:
  - Gazebo contact stiffness/damping parity fixes the missing-normal-force blocker without extra q6 preload.
  - The safe contact state is repeatable for 2 seconds with approximately 0.15-0.17 N per pad side on fresh readback.
  - No physical lift has yet been attempted under the stiffness mapping; transport remains blocked pending that proof.
next_command: Preregister EXP-093 and execute only the unchanged first 2 mm arm target with q6 fixed, physical cup-lift, lateral-drift, table-clearance, bilateral-contact, force, and provenance gates.
```

## Experiment EXP-093

```yaml
experiment_id: EXP-093
prior_experiment: EXP-092 VALID bilateral contact-only success
status: RUNNING
lifecycle: STIFF_TPU_FIRST_2MM_PHYSICAL_MICRO_LIFT
run_mode: continue_exact_bilateral_state_with_no_q6_change
hypothesis: The proven bilateral normal force carries the cup 1.5-2.5 mm upward under the unchanged first 2 mm arm target, clears table support, and retains bilateral contact.
single_variable: Execute only the previously frozen first 2 mm arm target; q6, model, scene, policy, controllers, session, epoch, and no-attachment physics contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00027779933025211256, 0.4726547692920405, 0.21490745392516858, 0.8548797168412275, 0.0004945303285419433]
  initial_q6_rad: -0.047408698226594014
  initial_cup_position_m: [0.020001916917135532, -0.2789656303399597, 0.1647117776592463]
  initial_pad_normal_force_n: [0.15194629020633726, 0.1519311127728159]
  lift_target_arm_rad: [-0.0002062266287315138, 0.46262046903357984, 0.21277364017949124, 0.8648894480356747, 0.0005764164414532356]
  lift_script: [/tmp/so101_exp093_micro_lift.py, 03835b526a0ef034f845722085763aae20c272b44307bcbbf189fb302452e60f]
  lift_gate_m: [0.0015, 0.0025]
  maximum_lateral_drift_m: 0.001
  maximum_force_n: 11.60
preconditions:
  - Same session/epoch is unpaused with active controllers, arm at CLOSE_READY, q6 held at the EXP-092 endpoint, continuous bilateral contact, table-supported upright cup, and force below the ceiling.
  - MoveIt world contains table, pedestal, and plastic_cup; the script may attach only the MoveIt collision shadow to gripper/jaw for planning and must not create any MuJoCo attachment or constraint.
  - Script hash matches and no command occurred after the fresh readback.
success_criteria:
  - Plan-to-execute drift is at most 0.01 rad and the arm reaches the frozen target.
  - Physical cup lift is 1.5-2.5 mm, lateral drift is at most 1 mm, table contact is absent, and bilateral fingertip contact remains continuous through execution and a 0.30-second hold.
  - Force remains at or below 11.60 N; session/epoch remain unchanged; no pause/reset, q6 change, simulator constraint, attachment, or object write occurs.
failure_criteria: Any planning, execution, physical lift, drift, table, contact, force, freshness, provenance, or evidence failure stops before further lift/transport.
invalid_criteria: Any unrecorded state/model/policy/q6/script change or hidden physical aid invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:10:05+08:00
  precondition_readback: Fresh joint and atomic evidence match the frozen arm/q6/cup/bilateral state with roughly 0.152 N normal force per side and unchanged unpaused epoch 0; script is lint-clean and hash-matched.
decision: PENDING. This transition occurs before MoveIt collision-shadow attach, planning, or arm execution.
next_experiment: Only a separately preregistered longer hold/lift/transport sequence after VALID physical micro-lift.
```

## Experiment EXP-093 Terminal Result

```yaml
experiment_id: EXP-093
status: VALID
terminal_result: FIRST_2MM_ARM_INCREMENT_COMPLETED_PHYSICAL_LIFT_FAILED
terminal_time: 2026-08-12T03:10:46+08:00
command: python3 /tmp/so101_exp093_micro_lift.py
exit_code: 1
result:
  plan_to_execute_drift_rad: 9.483820220031886e-10
  trajectory_points: 5
  controller_result: SUCCEEDED
  moveit_result: SUCCEEDED
  client_monitor_result: MOVEIT_EXECUTION_MONITOR_ABORTED
  terminal_arm_joints_rad: [-0.00014193927534699227, 0.4632179378559878, 0.21300391266869675, 0.8648224688566525, 0.0005062582799071364]
  terminal_q6_rad: -0.04740850706589985
  terminal_cup_position_m: [0.019998206843796027, -0.2792853751169185, 0.16471177953932317]
  physical_cup_lift_m: approximately_zero
  terminal_table_contact: true
  terminal_contact_counts: [1, 1]
  terminal_pad_normal_force_n: [0.15434181544322256, 0.15427501149629808]
  terminal_maximum_force_n: 0.1963032720829992
diagnosis:
  - The MoveIt plan and arm controller completed the target with negligible start drift, but the monitor observed transient bilateral-contact loss during motion and cancelled its action-result wait.
  - The pad contact points moved upward approximately 2 mm relative to the robot, while the cup stayed at table height; this is physical tangential slip rather than planner or controller failure.
  - Bilateral contact and the prior q6 recovered at rest. The approximately 0.154 N per-side normal force is sufficient for static contact but insufficient for this dynamic lift under the current contact solver.
evidence:
  micro_lift_log_sha256: e4dde132eac0f435ce403f5418a49344fe71c7a6cf53d4827c3b51ef3a09692e
  micro_lift_json_sha256: 9431e2b2125da3d1917f53b4f5029f37517b77dccb30e1d8e573cb77932f3502
  micro_lift_script_sha256: 03835b526a0ef034f845722085763aae20c272b44307bcbbf189fb302452e60f
decision: Preserve the exact endpoint and bilateral state. Increase only bounded gripper preload to a separately preregistered per-side normal-force target before another arm increment.
```

## Checkpoint CP-128

```yaml
checkpoint_id: CP-128
checkpoint_time: 2026-08-12T03:10:55+08:00
last_valid_experiment: EXP-093
current_hypothesis: Raising sustained pad normal force from approximately 0.154 N to 0.50 N per side, still far below the 11.60 N force limit and within q6 margin, will prevent tangential slip on the next 2 mm increment.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status remains empty. Same stiffness session/epoch is unpaused at the first arm endpoint with q6 unchanged and bilateral contact restored.
confirmed_conclusions:
  - Normal stiffness parity fixed contact generation but the minimal 0.05 N contact threshold was not a sufficient dynamic-lift threshold.
  - The first arm increment itself is valid and repeatable; the limiting variable remains pad normal preload.
  - q6=-0.04741 remains approximately 0.01219 rad above the safe lower bound, so a fine-step contact preload can be tested without returning to the old lower-limit route.
next_command: Preregister EXP-094 and apply only 20 microradian q6 decrements until both sides sustain at least 0.50 N for 2 seconds, with the same force, displacement, q6, provenance, and no-hidden-aid gates.
```

## Experiment EXP-094

```yaml
experiment_id: EXP-094
prior_experiment: EXP-093 VALID dynamic-slip physical-lift failure
status: RUNNING
lifecycle: STIFF_TPU_BOUNDED_PRELOAD_TO_DYNAMIC_FORCE_TARGET
run_mode: continue_exact_first_lift_endpoint_without_arm_motion
hypothesis: Fine q6 preload raises each side to at least 0.50 N sustained normal force before any safety bound, creating enough dynamic friction margin for the next lift increment.
single_variable: Apply only 20 microradian q6 decrements; arm, model, policy, scene, controllers, session, epoch, cup state, and no-attachment contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00014193927534699227, 0.4632179378559878, 0.21300391266869675, 0.8648224688566525, 0.0005062582799071364]
  initial_q6_rad: -0.04740850706589985
  initial_cup_position_m: [0.019998206843796027, -0.2792853751169185, 0.16471177953932317]
  initial_pad_normal_force_n: [0.15434181544322256, 0.15427501149629808]
  preload_script: [/tmp/so101_exp094_preload_only.py, 437df9d29f9c6ea483abf9706659a01d14321ff93dc14b24f5a66c26652f45e3]
  q6_step_rad: 0.00002
  target_per_side_normal_force_n: 0.50
  maximum_force_n: 11.60
  maximum_total_cup_displacement_m: 0.003
  stable_hold_s: 2.0
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - Same process/session/epoch is unpaused with active controllers, arm within 0.01 rad of the first lift target, q6 unchanged, bilateral contact restored, and the cup still table-supported.
  - Fresh force, cup, q6, arm, and provenance state match the frozen inputs; script is lint-clean and hash-matched.
  - No reset, pause, model/policy change, arm motion, object write, simulator constraint, or hidden aid occurred after EXP-093.
success_criteria:
  - Both sides reach and continuously sustain at least 0.50 N summed normal force for 2 seconds before q6 lower bound.
  - Force remains at or below 11.60 N, total cup displacement remains at or below 3 mm, bilateral contact remains continuous, and session/epoch remain unchanged.
  - No arm/lift motion, pause/reset, simulator attachment/constraint, or object write occurs.
failure_criteria: Any force, displacement, contact, q6, controller, freshness, provenance, or hold violation stops before another lift.
invalid_criteria: Any unrecorded state/script/model/policy change or hidden physical aid invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:12:40+08:00
  precondition_readback: Fresh terminal evidence matches the first lift endpoint with restored bilateral approximately 0.154 N per-side contact; script SHA is 437df9d2 and no action has occurred since readback.
decision: PENDING. This transition occurs before the first q6 preload step.
next_experiment: Separately preregister the next 2 mm arm increment only after VALID 0.50 N per-side hold success.
```

## Experiment EXP-094 Terminal Result

```yaml
experiment_id: EXP-094
status: INVALID
terminal_result: NONCONVERGENT_COMMAND_REFERENCE_SEMANTICS_OPERATOR_INTERRUPTED
terminal_time: 2026-08-12T03:15:42+08:00
command: python3 /tmp/so101_exp094_preload_only.py
exit_code: INTERRUPTED
result:
  completed_action_steps: 1102
  intended_q6_command_step_rad: 0.00002
  actual_q6_change_rad: -0.00007503687752452
  terminal_q6_rad: -0.04748354394342437
  terminal_pad_normal_force_n: [0.18117812328123303, 0.1811966311032288]
  terminal_maximum_force_n: 0.19630367153390685
  terminal_cup_position_m: [0.01999759101334119, -0.27928236812433704, 0.1647117766345833]
  terminal_contact_counts: [1, 1]
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The script calculated every next command as actual_q6 - 20 microradians. Contact compliance allowed only a small fraction of each requested delta, so the command reference did not accumulate and force rose only from approximately 0.154 N to 0.181 N after 1102 actions.
  - The intended experiment variable was the command-reference increment, not the constrained actual-position increment; the harness therefore did not implement the preregistered manipulation.
  - SIGINT stopped the owned script. The rclpy shutdown traceback is interruption cleanup noise; fresh joint and atomic evidence prove the simulator, controllers, bilateral contact, cup, force, session, and epoch remain healthy.
evidence:
  preload_log_sha256: 27c79d21f7e50553941378d616fe8bf57132656c9b3e275238acc09da21cca67
  preload_json_sha256: 7bd0bc57dad5c2361cea25c292994bf42a548db06f7766fa5ebec1fbac0bfac8
  preload_script_sha256: 437df9d29f9c6ea483abf9706659a01d14321ff93dc14b24f5a66c26652f45e3
decision: Do not use the 1102-step trajectory as calibration evidence. Preserve the exact stable terminal state and correct only command-target accumulation in a new preregistered experiment.
```

## Checkpoint CP-129

```yaml
checkpoint_id: CP-129
checkpoint_time: 2026-08-12T03:15:50+08:00
last_valid_experiment: EXP-093
last_invalid_experiment: EXP-094
current_hypothesis: Unchanged from CP-128; correctly accumulating the commanded q6 target by 20 microradians per action should reach the 0.50 N per-side force target in a bounded number of steps.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status is empty. Same stiffness stack remains unpaused at epoch 0 and first lift endpoint with bilateral contact.
confirmed_conclusions:
  - The invalid harness never approached any q6, force, cup-displacement, session, or epoch safety boundary.
  - Fresh terminal state is a safe continuation point with approximately 0.181 N per side and q6=-0.047484.
next_command: Preregister EXP-095 with only the command-target accumulation fix, then repeat the 0.50 N per-side static preload gate.
```

## Experiment EXP-095

```yaml
experiment_id: EXP-095
prior_experiment: EXP-094 INVALID command-reference semantics
status: RUNNING
lifecycle: STIFF_TPU_ACCUMULATED_COMMAND_PRELOAD_TO_DYNAMIC_FORCE_TARGET
run_mode: continue_exact_stable_state_with_corrected_command_target_accumulation
hypothesis: Accumulating the q6 command target by 20 microradians per action reaches 0.50 N per side within the safe q6/force/displacement envelope.
single_variable: Relative to invalid EXP-094, compute next_command_target = prior_command_target - 0.00002 rather than actual_q6 - 0.00002; all physical parameters, state, bounds, session, and policy remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00014195147731077947, 0.46321794942609174, 0.2130039252149725, 0.8648224810620887, 0.00050627588505617]
  initial_q6_rad: -0.04748354394342437
  initial_cup_position_m: [0.01999759101334119, -0.27928236812433704, 0.1647117766345833]
  initial_pad_normal_force_n: [0.18117812328123303, 0.1811966311032288]
  preload_script: [/tmp/so101_exp095_preload_only.py, efa22a8165b26d132b87026778e4ac44af961d1b7a7e0385d05c43cf89742b09]
  command_target_step_rad: 0.00002
  target_per_side_normal_force_n: 0.50
  maximum_force_n: 11.60
  maximum_total_cup_displacement_m: 0.003
  stable_hold_s: 2.0
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - Fresh joint and atomic evidence match the frozen arm/q6/cup/bilateral-force state with active controllers, unpaused physics, and epoch 0.
  - Script differs from EXP-094 only in evidence identity, frozen initial q6, and command-target accumulation semantics; it is lint-clean and hash-matched.
  - No action occurred after the fresh readback.
success_criteria:
  - Both sides continuously sustain at least 0.50 N for 2 seconds before any q6, force, displacement, contact, or provenance limit.
  - No arm/lift motion, reset/pause, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any action, q6, force, displacement, bilateral, hold, freshness, session, or epoch gate violation stops before lift.
invalid_criteria: Any unrecorded state/script/model/policy change or harness deviation invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:17:10+08:00
  precondition_readback: Fresh post-interrupt state matches CP-129; script SHA is efa22a81 and this transition occurs before its first accumulated command.
decision: PENDING.
next_experiment: Separately preregister the next arm increment only after VALID dynamic-force hold success.
```

## Experiment EXP-095 Terminal Result

```yaml
experiment_id: EXP-095
status: INVALID
terminal_result: FORCE_TARGET_REACHED_HOLD_REFERENCE_UNLOADED_PRELOAD
terminal_time: 2026-08-12T03:17:29+08:00
command: python3 /tmp/so101_exp095_preload_only.py
exit_code: 1
result:
  accumulated_command_steps: 50
  peak_left_normal_force_n: 0.5071763603545868
  peak_right_normal_force_n: 0.5089444156010975
  hold_command_semantics: target reset to constrained actual q6
  post_hold_left_normal_force_n: 0.49355559401612487
  post_hold_right_normal_force_n: 0.49344196943738095
  terminal_q6_rad: -0.04835171915507183
  terminal_cup_position_m: [0.019997359859817154, -0.2792475364435764, 0.1647117799173903]
  terminal_maximum_force_n: 0.49355559401612487
  terminal_contact_counts: [1, 1]
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - Correctly accumulated command targets reached the preregistered force threshold quickly and safely.
  - The subsequent hold used hold_target = actual_q6 instead of the final accumulated command target, intentionally or not removing controller position error and reducing pad force just below the 0.50 N gate.
  - Physical safety and provenance remained valid; only the hold-reference implementation failed to preserve the manipulated variable.
evidence:
  preload_log_sha256: cce878bae4f70a935a22ae43e5c63f9c6d5a3ed3b4b145bc54f38bf3755dfa22
  preload_json_sha256: 5ca3fa27bd27beb4f173296f3d461f8f8e6099213cf406dfdeac1481a09df1ed
  preload_script_sha256: efa22a8165b26d132b87026778e4ac44af961d1b7a7e0385d05c43cf89742b09
decision: Do not count the failed hold. Preserve the safe approximately 0.494 N bilateral state and correct only hold_target to the final command reference in a new experiment.
```

## Checkpoint CP-130

```yaml
checkpoint_id: CP-130
checkpoint_time: 2026-08-12T03:17:35+08:00
last_valid_experiment: EXP-093
last_invalid_experiment: EXP-095
current_hypothesis: Preserving the final accumulated q6 command target during the hold will keep both sides above 0.50 N for the required 2 seconds.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status remains empty. Same stiffness stack remains epoch 0 unpaused with bilateral contact and approximately 0.494 N per side.
confirmed_conclusions:
  - The 0.50 N target is physically reachable with large q6 and force safety margins.
  - Only the hold-reference assignment remains unqualified; no additional physics or model change is indicated.
next_command: Preregister EXP-096, add at most the required accumulated 20 microradian step(s), then hold the final command target unchanged for 2 seconds.
```

## Experiment EXP-096

```yaml
experiment_id: EXP-096
prior_experiment: EXP-095 INVALID hold-reference semantics
status: RUNNING
lifecycle: STIFF_TPU_PRESERVED_COMMAND_TARGET_DYNAMIC_FORCE_HOLD
run_mode: continue_exact_approximately_0_494N_bilateral_state
hypothesis: Holding the final accumulated q6 command reference unchanged preserves at least 0.50 N per side for 2 seconds.
single_variable: Relative to invalid EXP-095, use hold_target = final_command_target rather than constrained_actual_q6; all physical inputs, bounds, state, session, epoch, and policy remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_q6_rad: -0.04835171915507183
  initial_cup_position_m: [0.019997359859817154, -0.2792475364435764, 0.1647117799173903]
  initial_pad_normal_force_n: [0.49355559401612487, 0.49344196943738095]
  preload_script: [/tmp/so101_exp096_preload_hold.py, f42eec8e3b1ade34afe9f15eca6ddd1d047839c1b1fe2a4f3a00189df7f2784b]
  command_target_step_rad: 0.00002
  target_per_side_normal_force_n: 0.50
  maximum_force_n: 11.60
  maximum_total_cup_displacement_m: 0.003
  stable_hold_s: 2.0
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - Same session/epoch is unpaused with active controllers, unchanged arm endpoint, bilateral contact, q6 and cup state matching the frozen readback.
  - Script differs from EXP-095 only in evidence identity, frozen initial q6, and preserved hold command target; it is lint-clean and hash-matched.
  - No action occurred after the fresh readback.
success_criteria:
  - Both sides sustain at least 0.50 N continuously for 2 seconds below q6, force, displacement, and provenance limits.
  - No arm/lift motion, reset/pause, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any action, q6, force, displacement, bilateral, hold, freshness, session, or epoch gate violation stops before lift.
invalid_criteria: Any unrecorded state/script/model/policy change or harness deviation invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:19:05+08:00
  precondition_readback: Fresh state matches CP-130 and script SHA f42eec8e; this transition occurs before its first action.
decision: PENDING.
next_experiment: Separately preregister the next arm increment only after VALID hold success.
```

## Experiment EXP-096 Terminal Result

```yaml
experiment_id: EXP-096
status: VALID
terminal_result: DYNAMIC_FORCE_PRELOAD_HOLD_PROVED
terminal_time: 2026-08-12T03:19:24+08:00
command: python3 /tmp/so101_exp096_preload_hold.py
exit_code: 0
result:
  terminal_q6_rad: -0.048409838154160216
  hold_duration_s: 2.0
  hold_sample_count: 168
  left_normal_force_range_n: [0.5105708587952289, 0.5146084511573616]
  right_normal_force_range_n: [0.5114243944835039, 0.5146383290016993]
  maximum_normal_force_n: 0.5146383290016993
  terminal_contact_counts: [1, 1]
  terminal_cup_position_m: [0.019997154883470834, -0.2792452077011229, 0.16471177632015876]
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - Preserving the final q6 command reference maintains the desired actuator preload and eliminates the EXP-095 force drop.
  - The 0.50 N per-side dynamic-force target is stable with q6 still more than 0.011 rad above its safe lower bound, force below 5 percent of the ceiling, and total cup displacement below 3 mm.
evidence:
  preload_log_sha256: cf5f7179eb78f6ab407029e2a63224ec2d3f55adf004935f29d10ac65ba9a875
  preload_json_sha256: 76f24cacb730701d1a9652d524e59267318ed5525f9477f09982aff0392e2969
  preload_script_sha256: f42eec8e3b1ade34afe9f15eca6ddd1d047839c1b1fe2a4f3a00189df7f2784b
decision: Preserve the exact live state and preregister the next frozen 2 mm arm increment without changing q6 or any model/policy parameter.
```

## Checkpoint CP-131

```yaml
checkpoint_id: CP-131
checkpoint_time: 2026-08-12T03:19:30+08:00
last_valid_experiment: EXP-096
current_hypothesis: The stable approximately 0.514 N per-side preload prevents the prior tangential slip and carries the cup during the next 2 mm arm increment.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status remains empty. Same stiffness stack/session/epoch remains unpaused at the first arm endpoint with q6=-0.04841 and bilateral preload held.
confirmed_conclusions:
  - Contact stiffness parity plus preserved controller command reference produces a stable, bounded dynamic grasp preload.
  - The next experiment can isolate arm motion without additional q6 or model changes.
next_command: Preregister EXP-097 and execute only the frozen next 2 mm arm target with physical lift, table-clearance, bilateral, force, drift, and provenance gates.
```

## Experiment EXP-097

```yaml
experiment_id: EXP-097
prior_experiment: EXP-096 VALID dynamic-force preload hold
status: RUNNING
lifecycle: STIFF_TPU_SECOND_2MM_PHYSICAL_MICRO_LIFT
run_mode: continue_exact_dynamic_preload_state_without_q6_change
hypothesis: The approximately 0.514 N per-side preload carries the cup 1.5-2.5 mm upward through the frozen second 2 mm arm target, clears table support, and retains bilateral contact.
single_variable: Execute only the frozen next arm target; q6 command reference, model, policy, scene, controllers, session, epoch, and no-attachment physics contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_arm_joints_rad: [-0.0001419546530401199, 0.46321808606063997, 0.21300406080492312, 0.8648226172736213, 0.0005062800969728916]
  initial_q6_rad: -0.048409837808327805
  initial_cup_position_m: [0.019996997440378833, -0.2792452127156752, 0.16471177647714613]
  initial_pad_normal_force_n: [0.5145172623277582, 0.5145457492379995]
  lift_target_arm_rad: [-0.0002059614124630276, 0.4530466639711597, 0.21089465616398247, 0.8748565203763494, 0.0005761294179064712]
  lift_script: [/tmp/so101_exp097_micro_lift.py, 4d90cb9573afc390d228254d6378a7afcedec45f761c36454c2246dba1334f99]
  lift_gate_m: [0.0015, 0.0025]
  maximum_lateral_drift_m: 0.001
  maximum_force_n: 11.60
preconditions:
  - Same process/session/epoch is unpaused with active controllers, arm at the prior lift endpoint, preserved q6 command preload, bilateral approximately 0.514 N contacts, and table-supported cup.
  - MoveIt collision shadow remains attached only in Planning Scene; no MuJoCo attachment or constraint exists.
  - Script is lint-clean and hash-matched; no action occurred after fresh readback.
success_criteria:
  - Plan-to-execute drift is at most 0.01 rad and arm reaches the frozen target.
  - Cup rises 1.5-2.5 mm with at most 1 mm lateral drift, clears table contact, retains bilateral contact through execution and 0.30-second hold, and stays below 11.60 N.
  - Session/epoch and q6 remain unchanged; no pause/reset, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any planning, execution, lift, drift, table, bilateral, force, q6, freshness, provenance, or evidence violation stops before further motion.
invalid_criteria: Any unrecorded state/script/model/policy change or hidden physical aid invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:20:35+08:00
  precondition_readback: Fresh state matches CP-131 with approximately 0.514 N per side and unchanged q6/session/epoch; script SHA is 4d90cb95 and this transition occurs before planning.
decision: PENDING.
next_experiment: Long hold and formal LIFT/transport only after VALID physical micro-lift.
```

## Experiment EXP-097 Terminal Result

```yaml
experiment_id: EXP-097
status: VALID
terminal_result: ARM_INCREMENT_EXECUTED_BUT_CUP_TANGENTIAL_SLIP_PERSISTS
terminal_time: 2026-08-12T03:22:15+08:00
command: python3 /tmp/so101_exp097_micro_lift.py
exit_code: 1
result:
  lift_trajectory_points: 6
  plan_to_execute_drift_rad: 5.6535575862753235e-09
  terminal_arm_joints_rad: [-0.00015205554902928634, 0.45367375704283847, 0.21112832610769589, 0.874785554158837, 0.0005531937106397004]
  terminal_q6_rad: -0.04840961567114686
  cup_vertical_displacement_m: 9.946035553765054e-07
  terminal_cup_position_m: [0.019996842124513685, -0.2795509976020785, 0.16471177692330288]
  terminal_pad_normal_force_n: [0.5171833164689629, 0.5171420480585373]
  terminal_contact_counts: [1, 1]
  terminal_other_contact_geoms: [table_collision]
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The arm reached the intended approximately 2 mm upward TCP increment; offline kinematic readback confirms the TCP rose approximately 1.997 mm.
  - Bilateral pad contact and approximately 0.517 N normal force per side remained present, but the cup wall slipped tangentially between the pads and the cup stayed table-supported.
  - Both pads contact opposite faces of the same thin wall_near_collision cup wall. The contact pair is physical and constraint-free, but the 0.50 N per-side preload is not a sufficient dynamic carry margin for this geometry.
  - No pause/reset, MuJoCo constraint/attachment, direct object state write, or hidden aid occurred.
evidence:
  lift_log_sha256: 205058b0ee0a7e879190842ae5ec6fd20b68bf0530794d77d9e8d0da45fee281
  lift_json_sha256: 3123512269bfe45ecf9056e09150e6d20d46d8e09681be2856b1473c9df986a8
  lift_script_sha256: 4d90cb9573afc390d228254d6378a7afcedec45f761c36454c2246dba1334f99
decision: Preserve the exact live state. Increase only the bounded bilateral preload target before attempting another separately preregistered arm increment.
```

## Checkpoint CP-132

```yaml
checkpoint_id: CP-132
checkpoint_time: 2026-08-12T03:24:30+08:00
last_valid_experiment: EXP-097
current_hypothesis: Raising the physical preload from approximately 0.517 N to 1.00 N per side will provide sufficient tangential carry margin without changing model contact parameters.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status remains empty. Same stiffness stack/session/epoch is unpaused at the EXP-097 arm endpoint with q6=-0.048410, continuous bilateral contact, and a table-supported cup.
confirmed_conclusions:
  - The joint-space lift target and controller execution are correct; the remaining failure is physical tangential slip at the cup wall contact.
  - Current force is under 5 percent of the 11.60 N ceiling and q6 remains more than 0.011 rad above its lower bound, so a bounded force-only calibration retains substantial safety margin.
next_command: Preregister EXP-098 and increase only q6 command preload in 20 microradian steps until both sides sustain 1.00 N for 2 seconds.
```

## Experiment EXP-098

```yaml
experiment_id: EXP-098
prior_experiment: EXP-097 VALID tangential-slip failure
status: RUNNING
lifecycle: STIFF_TPU_ONE_NEWTON_BILATERAL_PRELOAD_HOLD
run_mode: continue_exact_EXP097_terminal_state_without_arm_motion
hypothesis: A preserved q6 command reference producing at least 1.00 N normal force per side remains stable for 2 seconds inside all force, q6, displacement, and provenance bounds.
single_variable: Raise only the per-side normal-force target from approximately 0.517 N to 1.00 N by bounded q6 command increments; model, policy, arm target, scene, controllers, session, epoch, and no-attachment physics contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00015205554902928634, 0.45367375704283847, 0.21112832610769589, 0.874785554158837, 0.0005531937106397004]
  initial_q6_rad: -0.04840961567114686
  initial_cup_position_m: [0.019996842124513685, -0.2795509976020785, 0.16471177692330288]
  initial_pad_normal_force_n: [0.5171833164689629, 0.5171420480585373]
  preload_script: [/tmp/so101_exp098_preload_hold.py, 0f0b98335a3dfefb1754e000c54d07c4be234b54bb7b8ed6a1cc06404d3b2909]
  command_target_step_rad: 0.00002
  target_per_side_normal_force_n: 1.00
  stable_hold_s: 2.0
  maximum_force_n: 11.60
  maximum_run_relative_cup_displacement_m: 0.003
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - Same process/session/epoch is unpaused with active controllers, arm at EXP-097 endpoint, bilateral approximately 0.517 N contacts, and cup still table-supported.
  - Script is lint-clean and SHA-matched; no arm/lift motion, model change, reset, pause, attachment, constraint, or object write is included.
  - No physical action occurred after the fresh frozen readback.
success_criteria:
  - Both sides continuously sustain at least 1.00 N for 2 seconds before any q6, force, displacement, contact, or provenance bound.
  - Arm remains at the frozen endpoint and the run contains no lift, pause/reset, simulator constraint/attachment, object write, or hidden aid.
failure_criteria: Any action, q6, force, displacement, bilateral, hold, freshness, session, epoch, or arm-state gate violation stops before lift.
invalid_criteria: Any unrecorded state/script/model/policy change or harness deviation invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:25:25+08:00
  precondition_readback: Fresh state matches CP-132 and script SHA 0f0b9833; this transition occurs before its first q6 command.
decision: PENDING.
next_experiment: Separately preregister the next arm increment only after VALID 1.00 N hold success.
```

## Experiment EXP-098 Terminal Result

```yaml
experiment_id: EXP-098
status: VALID
terminal_result: ONE_NEWTON_BILATERAL_PRELOAD_HOLD_PROVED
terminal_time: 2026-08-12T03:26:35+08:00
command: python3 /tmp/so101_exp098_preload_hold.py
exit_code: 0
result:
  terminal_q6_rad: -0.04948697936088109
  hold_duration_s: 2.0
  hold_sample_count: 168
  left_normal_force_range_n: [1.0172414414011424, 1.0282264019389147]
  right_normal_force_range_n: [1.0191808495642216, 1.0283091296735294]
  maximum_normal_force_n: 1.0282264019389147
  terminal_cup_position_m: [0.019996571780144457, -0.2794948429952216, 0.16471177989354552]
  terminal_other_contact_geoms: [table_collision]
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - Accumulating and preserving the q6 command reference safely establishes more than 1.00 N normal force on both sides for the full 2-second window.
  - q6 remains approximately 0.0101 rad above its lower bound, maximum force is below 9 percent of the 11.60 N ceiling, and the arm stayed at the frozen endpoint.
  - Cup displacement during this force-only calibration remained bounded and the cup is still table-supported as required before the next lift probe.
evidence:
  preload_log_sha256: 9230c16fb466c1f903021fc6da8f46b003fe7ce0b4e837a6421e65480a0a5fa0
  preload_json_sha256: 310bdff356b1d60b8e35160a8ff124021a08e8d62eb6413cb4eca84321c932a9
  preload_script_sha256: 0f0b98335a3dfefb1754e000c54d07c4be234b54bb7b8ed6a1cc06404d3b2909
decision: Preserve this exact dynamic preload and compute a fresh collision-aware world-Z plus 2 mm IK target without sending a physical action.
```

## Checkpoint CP-133

```yaml
checkpoint_id: CP-133
checkpoint_time: 2026-08-12T03:29:45+08:00
last_valid_experiment: EXP-098
current_hypothesis: The 1.00 N per-side dynamic preload supplies enough tangential carry margin for a fresh 2 mm world-Z lift while retaining the no-constraint physical contract.
working_tree_status: Same intentional source/model/test/plan/ledger/fork state; protected Gazebo tracked status remains empty. Same stiffness stack/session/epoch is unpaused, arm is unchanged from EXP-097, q6=-0.049487, and bilateral preload is stable.
confirmed_conclusions:
  - A read-only MoveIt /compute_ik query produced a fresh collision-aware target exactly 2 mm above the live so101_tcp pose while preserving orientation.
  - The IK query performed no physical command and did not change the frozen live state.
next_command: Preregister EXP-099 and execute only the fresh world-Z plus 2 mm arm target with physical lift, table-clearance, bilateral, force, drift, and provenance gates.
```

## Experiment EXP-099

```yaml
experiment_id: EXP-099
prior_experiment: EXP-098 VALID one-newton preload hold
status: RUNNING
lifecycle: ONE_NEWTON_PRELOAD_PHYSICAL_MICRO_LIFT
run_mode: continue_exact_EXP098_terminal_state_without_q6_change
hypothesis: The 1.00 N per-side preload carries the cup 1.5-2.5 mm upward through the fresh 2 mm world-Z TCP target, clears table support, and retains bilateral physical contact.
single_variable: Execute only the fresh collision-aware arm IK target; q6 command reference, model, policy, scene, controllers, session, epoch, and no-attachment physics contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-stiffness
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00015199328232715195, 0.453674790144152, 0.21112935823295967, 0.87478658720256, 0.0005531032222654058]
  initial_q6_rad: -0.04948697748447818
  target_tcp_world_position_m: [0.020663208534545188, -0.26327236426852874, 0.20647326190362447]
  target_tcp_world_orientation_xyzw: [-0.01103644023320002, -0.011032814797183174, -0.7067686644408122, 0.7072725987546675]
  lift_target_arm_rad: [-0.0001518459411565051, 0.44180293901908685, 0.21326783756034987, 0.8824699829881489, 0.0005551409688084152]
  lift_script: [/tmp/so101_exp099_micro_lift.py, 993f8af62c4847aaabd45e29c6b83375546928600a7cb27831570fb7b8457210]
  lift_gate_m: [0.0015, 0.0025]
  maximum_lateral_drift_m: 0.001
  maximum_force_n: 11.60
preconditions:
  - Same process/session/epoch is unpaused with active controllers, arm/q6 matching the frozen readback, stable bilateral at least 1.00 N contacts, and a table-supported cup.
  - MoveIt collision shadow remains attached only in Planning Scene; no MuJoCo attachment or constraint exists.
  - Script is lint-clean and SHA-matched; the IK query was read-only and no action occurred after the frozen state.
success_criteria:
  - Plan-to-execute drift is at most 0.01 rad and arm reaches the frozen target.
  - Cup rises 1.5-2.5 mm with at most 1 mm lateral drift, clears table contact, retains bilateral contact through execution and a 0.30-second hold, and stays below 11.60 N.
  - Session/epoch and q6 remain unchanged; no pause/reset, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any planning, execution, lift, drift, table, bilateral, force, q6, freshness, provenance, or evidence violation stops before further motion.
invalid_criteria: Any unrecorded state/script/model/policy change or hidden physical aid invalidates the run.
evidence_root: /tmp/so101-task13-stiffness
runtime_start:
  time: 2026-08-12T03:30:56+08:00
  precondition_readback: Fresh state and read-only IK response match CP-133; script SHA is 993f8af6 and this transition occurs before planning.
decision: PENDING.
next_experiment: Long physical hold and formal LIFT/transport only after VALID micro-lift success.
```

## Experiment EXP-099 Terminal Result

```yaml
experiment_id: EXP-099
status: VALID
terminal_result: ONE_NEWTON_PRELOAD_STILL_SLIPS_UNDER_2MM_WORLD_Z_LIFT
terminal_time: 2026-08-12T03:32:05+08:00
command: python3 /tmp/so101_exp099_micro_lift.py
exit_code: 1
result:
  lift_trajectory_points: 6
  plan_to_execute_drift_rad: 1.0888965246732933e-07
  terminal_arm_joints_rad: [-0.00011112963628103875, 0.44227711898811156, 0.2135541250576643, 0.8823944892632424, 0.0005577176091286036]
  terminal_q6_rad: -0.04948564659912027
  cup_vertical_displacement_m: 0.000002225513098974563
  terminal_cup_position_m: [0.019992715909378792, -0.2794056348922437, 0.1647117840346462]
  terminal_pad_normal_force_sum_n: [1.0456098344089622, 1.045681135548228]
  terminal_contact_counts: [1, 2]
  terminal_other_contact_geoms: [table_collision]
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The arm reached the fresh world-Z plus 2 mm target with negligible plan-to-execute drift while bilateral normal preload remained approximately 1.046 N total per side.
  - The cup still rose only approximately 2.2 micrometres and remained table-supported, so merely doubling preload did not address the physical failure.
  - Static model inspection confirms contact dimension 3 and mixed sliding friction 3.0 on the fingertip/cup pairs; the missing mechanism is not an absent friction coefficient or absent tangential dimension.
  - MuJoCo's default noslip_iterations=0 disables the post-solver intended to suppress friction-dimension slip/drift from soft constraints. This matches the observed slow tangential creep despite valid bilateral normal contacts.
evidence:
  lift_log_sha256: 8ed957a6d12271f35a4d70653fa014d39842e1f4b486e367a5ca3ad10fd0c4df
  lift_json_sha256: 14b9751fe7e2e272a50562615ad5467f99995770cd132816280e0b28f1843cd6
  lift_script_sha256: 993f8af62c4847aaabd45e29c6b83375546928600a7cb27831570fb7b8457210
decision: Stop increasing q6 preload. Add an explicit bounded MuJoCo Noslip post-solver budget as the next single model variable, then repeat the physical sequence from a fresh reset stack.
```

## Checkpoint CP-134

```yaml
checkpoint_id: CP-134
checkpoint_time: 2026-08-12T03:34:45+08:00
last_valid_experiment: EXP-099
current_hypothesis: Enabling ten Noslip post-solver iterations will suppress the observed friction-dimension drift so the already-sufficient physical friction and normal force can carry the cup.
working_tree_status: Main worktree adds an intentional red-then-green MJCF option test and scene noslip_iterations=10; protected Gazebo tracked status remains empty. Old stiffness stack remains unpaused only until the fresh model stack replaces it.
confirmed_conclusions:
  - Official MuJoCo XML reference defines noslip_iterations as a post-processing solver for suppressing slip/drift in friction dimensions and documents default zero as disabled.
  - New test failed RED at the default zero, then all 10 visual/model parity tests passed after adding the explicit bounded value 10.
  - Source and isolated install scene hashes match exactly.
next_command: Preregister EXP-100, replace the old stack with the isolated noslip overlay, verify exact process/model provenance, and reach formal CLOSE_READY on a fresh session before any contact calibration.
```

## Experiment EXP-100

```yaml
experiment_id: EXP-100
prior_experiment: EXP-099 VALID friction-dimension-slip failure
status: RUNNING
lifecycle: NOSLIP_MODEL_FRESH_STACK_AND_CLOSE_READY
run_mode: replace_old_stack_then_formal_scene_and_staged_approach
hypothesis: The same model with only noslip_iterations=10 starts cleanly, preserves ResetWorld/scene/robot behavior, and reaches CLOSE_READY without early contact or cup displacement.
single_variable: Relative to EXP-099, set MuJoCo option noslip_iterations from implicit default 0 to explicit 10. Friction, solref, mass, inertias, geometry, controller, q6 bounds, approach policy, timestep, gravity, and no-attachment contract remain unchanged.
frozen_inputs:
  parent_head: eabe88885bf802fb14968547634fd06c26c1b38a
  fork_commit: 20c77cd71305556cb5c914b07e8d5a4d40d5f3fd
  runtime_fork_install: /tmp/so101-fork-reset-test/install
  demo_install: /tmp/so101-noslip-20260812/overlay/install
  scene_mjcf_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  model_test_sha256: dc71207fe577ba0a749d95e0780d5d74cfcac8ad6fa5dc7b685cd3bb31b77f79
  motion_policy_sha256: 303044acea71039f74693e5f0e0d97f3adbaf21c95745c57aa63709fc4c6f321
  static_test_result: 10 passed
  ros_domain_id: 149
  simulation_session_id: so101-task13-noslip
  expected_reset_epoch: 0
preconditions:
  - Source/install scene hashes match; all focused model parity tests pass; protected Gazebo tracked status is empty.
  - Old owned sim and MoveIt processes will be stopped before starting the new session; no unrelated process or user work is targeted.
  - Formal scene setup and staged approach use the same installed code/policy and explicit execution gate as EXP-091.
success_criteria:
  - New process command resolves to the fork runtime and noslip overlay scene, publishes session so101-task13-noslip at epoch 0, and has both controllers active.
  - Formal Planning Scene contains exactly table, pedestal, and the 13-part cup collision object; staged approach reaches CLOSE_READY through 15 segments.
  - No early fingertip contact, excessive cup displacement, pause/reset, hidden constraint, attachment, object write, or provenance mismatch occurs.
failure_criteria: Any process, model, launch, controller, evidence, scene, approach, contact, displacement, or provenance gate violation stops before contact calibration.
invalid_criteria: Any unrecorded model/policy/code change or failure to replace the old owned process invalidates the run.
evidence_root: /tmp/so101-task13-noslip
runtime_start:
  time: 2026-08-12T03:35:49+08:00
  precondition_readback: Static RED/GREEN and isolated build evidence are complete; this transition occurs before stopping the old stack or starting the new model.
decision: PENDING.
next_experiment: Preregister bounded bilateral preload only after VALID CLOSE_READY.
```

## Experiment EXP-100 Terminal Result

```yaml
experiment_id: EXP-100
status: VALID
terminal_result: NOSLIP_STACK_PROVENANCE_AND_CLOSE_READY_PASSED
terminal_time: 2026-08-12T03:38:55+08:00
commands:
  - command: start simulation and MoveIt/RViz with isolated noslip overlay
    exit_code: 0
  - command: ros2 run so101_mujoco_demo_py scene_setup
    exit_code: 0
  - command: staged_approach --mode execute --execute --stop-after DESCEND
    exit_code: 0
result:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  simulator_process: /tmp/so101-fork-reset-test/install/lib/mujoco_ros2_control/ros2_control_node
  robot_state_publisher_scene: /tmp/so101-noslip-20260812/overlay/install/so101_mujoco_demo_py/share/so101_mujoco_demo_py/mjcf/scene.xml
  move_group_scene: /tmp/so101-noslip-20260812/overlay/install/so101_mujoco_demo_py/share/so101_mujoco_demo_py/mjcf/scene.xml
  active_controllers: [joint_state_broadcaster, arm_controller, gripper_controller]
  planning_scene_verified: true
  staged_approach_status: CLOSE_READY
  staged_approach_segments: 15
  terminal_joints_rad: [-0.0002534309461740592, 0.4727271845281081, 0.21489824823558118, 0.8549141172788711, 0.0005597648469939641, 0.4650364539746299]
  terminal_cup_position_m: [0.020000000000000007, -0.28, 0.16480156647042168]
  terminal_fingertip_contacts: [0, 0]
  terminal_other_contact_geoms: [table_collision]
  terminal_paused: false
diagnosis:
  - The old owned stack was cleanly stopped and replaced; simulator, robot_state_publisher, and move_group all resolve to the exact fork/noslip model provenance.
  - Formal scene setup reports pedestal 1, plastic_cup 13, and table 1 primitives, and staged approach completes all 15 selected segments with zero close-gripper calls.
  - No early fingertip contact or cup displacement occurred; the Noslip option does not regress startup, ResetWorld provenance, controller activation, Planning Scene, or free-space approach behavior.
evidence:
  staged_approach_log_sha256: cb46ca1fb6f144ddb611983cbd63dbc152576071d181f5e15fa5fc398bfd737b
  staged_approach_json_sha256: da3f3c0ebd29b70d8f0359deba04aa23756df732aa860a513dc278b7792031d9
decision: Preserve exact CLOSE_READY state and separately preregister the same approximately 0.50 N bilateral preload used before the slip probe.
```

## Checkpoint CP-135

```yaml
checkpoint_id: CP-135
checkpoint_time: 2026-08-12T03:39:30+08:00
last_valid_experiment: EXP-100
current_hypothesis: The Noslip stack can reproduce the same bounded 0.50 N per-side grasp preload before isolating its effect on tangential carry.
working_tree_status: Same intentional noslip source/test/model/plan/ledger/fork state; protected Gazebo tracked status remains empty. New noslip stack is epoch 0 unpaused at formal CLOSE_READY with no fingertip contact.
confirmed_conclusions:
  - Runtime provenance and the free-space/planning path are qualified on the new model.
  - The next manipulation changes only q6, permits bounded unilateral seating, accumulates command targets rather than constrained feedback, and preserves the final command reference through hold.
next_command: Preregister EXP-101 and establish at least 0.50 N per side for 2 seconds without arm motion.
```

## Experiment EXP-101

```yaml
experiment_id: EXP-101
prior_experiment: EXP-100 VALID noslip CLOSE_READY
status: RUNNING
lifecycle: NOSLIP_HALF_NEWTON_BILATERAL_CONTACT_HOLD
run_mode: continue_exact_CLOSE_READY_with_bounded_q6_only
hypothesis: The Noslip model reaches and sustains at least 0.50 N normal force per fingertip side for 2 seconds within the same q6, force, displacement, and provenance bounds.
single_variable: From CLOSE_READY, move only q6 through the reviewed coarse-to-fine contact search and preserve the final accumulated command reference. Arm/model/policy/scene/controllers/session/epoch remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [-0.0002534309461740592, 0.4727271845281081, 0.21489824823558118, 0.8549141172788711, 0.0005597648469939641]
  initial_q6_rad: 0.4650364539746299
  initial_cup_position_m: [0.020000000000000007, -0.28, 0.16480156647042168]
  contact_script: [/tmp/so101_exp101_contact_hold.py, aef8015590ee0087652dab1d537d523385a7136f340e9b62c10c87404bc3da74]
  coarse_start_q6_rad: -0.040
  nominal_contact_q6_rad: -0.047608632840292
  coarse_step_rad: 0.0005
  fine_command_target_step_rad: 0.00002
  target_per_side_normal_force_n: 0.50
  stable_hold_s: 2.0
  maximum_force_n: 11.60
  maximum_cup_displacement_m: 0.003
  safe_q6_lower_rad: -0.059600220867817
preconditions:
  - Same process/session/epoch is unpaused with active controllers, arm/q6/cup matching CP-135, zero fingertip contact, and formal Planning Scene present.
  - Script permits physical unilateral seating but rejects displacement, force, q6, contact-loss-during-hold, provenance, arm, and action violations.
  - Script is lint-clean and SHA-matched; no action occurred after the frozen state.
success_criteria:
  - Both sides continuously sustain at least 0.50 N for 2 seconds before any q6, force, displacement, contact, or provenance limit.
  - Arm remains at CLOSE_READY and no pause/reset, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any action, q6, force, displacement, bilateral, hold, freshness, session, epoch, or arm-state gate violation stops before lift.
invalid_criteria: Any unrecorded state/script/model/policy change or harness deviation invalidates the run.
evidence_root: /tmp/so101-task13-noslip
runtime_start:
  time: 2026-08-12T03:40:14+08:00
  precondition_readback: Fresh CLOSE_READY state matches CP-135 and script SHA aef80155; this transition occurs before its first q6 command.
decision: PENDING.
next_experiment: Separately preregister fresh world-Z plus 2 mm lift only after VALID hold success.
```

## Experiment EXP-101 Terminal Result

```yaml
experiment_id: EXP-101
status: VALID
terminal_result: NOSLIP_HALF_NEWTON_BILATERAL_HOLD_PROVED
terminal_time: 2026-08-12T03:41:30+08:00
command: python3 /tmp/so101_exp101_contact_hold.py
exit_code: 0
result:
  terminal_q6_rad: -0.04850795863514208
  hold_duration_s: 2.0
  hold_sample_count: 202
  left_normal_force_range_n: [0.5098984454701994, 0.5107558378636932]
  right_normal_force_range_n: [0.6235696582013133, 0.6250287805812613]
  maximum_normal_force_n: 0.6219057559081005
  terminal_cup_position_m: [0.019999883392508622, -0.278909877513529, 0.16492155313910403]
  terminal_other_contact_geoms: [table_collision]
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The reviewed coarse-to-fine q6 search physically seats the cup and preserves the final command reference, producing continuous bilateral force above 0.50 N for the full 2-second window.
  - q6, force, cumulative cup displacement, session, epoch, arm state, and no-hidden-aid bounds all pass.
  - This force level matches the approximately 0.50 N preload that slipped in EXP-097, allowing the next lift to isolate the Noslip model change rather than increased grasp force.
evidence:
  contact_log_sha256: 4700ade53e351ce3c18ae9cf82581091353cbe241e6e24fccabefb0383fba4a0
  contact_json_sha256: 2e92facb9b9bd05bcca451727cd1f63a869d605a8657e13592b8a42cce42b7a4
  contact_script_sha256: aef8015590ee0087652dab1d537d523385a7136f340e9b62c10c87404bc3da74
decision: Preserve exact live preload. Use the previously validated first 2 mm lift joint target because the read-only position-only IK service returned a distant branch and the constrained retry correctly failed closed.
```

## Checkpoint CP-136

```yaml
checkpoint_id: CP-136
checkpoint_time: 2026-08-12T03:43:30+08:00
last_valid_experiment: EXP-101
current_hypothesis: Noslip post-processing will let the same approximately 0.50 N bilateral preload carry the cup through the already validated first 2 mm lift target.
working_tree_status: Same intentional noslip source/test/model/plan/ledger/fork state; protected Gazebo tracked status remains empty. Noslip stack is epoch 0 unpaused at CLOSE_READY with q6=-0.048508 and stable bilateral contact.
confirmed_conclusions:
  - Unconstrained position-only /compute_ik returned a distant joint branch, and adding plus/minus 0.05 rad joint constraints correctly rejected it; neither read-only query changed physical state.
  - The frozen EXP-093 first-lift joint target already represents the local approximately plus 2 mm world-Z motion from the same CLOSE_READY configuration and is reused without modification.
next_command: Preregister EXP-102, attach only the MoveIt collision shadow, and execute the frozen first 2 mm target with physical outcome gates.
```

## Experiment EXP-102

```yaml
experiment_id: EXP-102
prior_experiment: EXP-101 VALID half-newton bilateral hold
status: RUNNING
lifecycle: NOSLIP_HALF_NEWTON_PHYSICAL_MICRO_LIFT
run_mode: continue_exact_EXP101_terminal_state_without_q6_change
hypothesis: With noslip_iterations=10, the approximately 0.51/0.62 N bilateral preload carries the cup 1.5-2.5 mm upward, clears table support, and retains physical fingertip contact.
single_variable: Execute only the previously validated first 2 mm arm target under the Noslip model; q6 command reference, friction, solref, mass, geometry, policy, controllers, session, and epoch remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [-0.0002502966785858475, 0.4727777913248263, 0.21489935872368246, 0.8548916790786721, 0.0005597798308855102]
  initial_q6_rad: -0.04850794875050089
  initial_cup_position_m: [0.019999883392508622, -0.278909877513529, 0.16492155313910403]
  initial_pad_normal_force_range_n: [[0.5098984454701994, 0.5107558378636932], [0.6235696582013133, 0.6250287805812613]]
  lift_target_arm_rad: [-0.0002062266287315138, 0.46262046903357984, 0.21277364017949124, 0.8648894480356747, 0.0005764164414532356]
  lift_script: [/tmp/so101_exp102_micro_lift.py, f2afbdd44ac92907812ce617c35c234857a9a3f576d0b7557cf33650721d77d1]
  lift_gate_m: [0.0015, 0.0025]
  maximum_lateral_drift_m: 0.001
  maximum_force_n: 11.60
preconditions:
  - Same process/session/epoch is unpaused with active controllers, arm/q6/cup and stable bilateral force matching CP-136.
  - Script applies and read-backs only a MoveIt Planning Scene collision shadow on gripper with touch links gripper/jaw; it makes no MuJoCo attachment, constraint, or object state write.
  - Script is lint-clean and SHA-matched; no physical action occurred after the frozen state.
success_criteria:
  - Planning Scene shadow converges, plan-to-execute drift is at most 0.01 rad, and arm reaches the frozen target.
  - Cup rises 1.5-2.5 mm with at most 1 mm lateral drift, clears table contact, retains bilateral contact through execution and a 0.30-second hold, and stays below 11.60 N.
  - Session/epoch and q6 remain unchanged; no pause/reset, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any planning, execution, lift, drift, table, bilateral, force, q6, freshness, provenance, or evidence violation stops before further motion.
invalid_criteria: Any unrecorded state/script/model/policy change or physical attachment aid invalidates the run.
evidence_root: /tmp/so101-task13-noslip
runtime_start:
  time: 2026-08-12T03:44:07+08:00
  precondition_readback: Fresh state matches CP-136; script SHA is f2afbdd4 and this transition occurs before Planning Scene mutation or arm planning.
decision: PENDING.
next_experiment: Ten-second physical hold and formal LIFT only after VALID micro-lift success.
```

## Experiment EXP-102 Terminal Result

```yaml
experiment_id: EXP-102
status: VALID
terminal_result: NOSLIP_PHYSICAL_MICRO_LIFT_PROVED
terminal_time: 2026-08-12T03:45:02+08:00
command: python3 /tmp/so101_exp102_micro_lift.py
exit_code: 0
result:
  moveit_attached_ids: [plastic_cup]
  moveit_world_ids_after_attach: [pedestal, table]
  lift_trajectory_points: 6
  plan_to_execute_drift_rad: 2.394127788813566e-11
  physical_micro_lift_m: 0.001962676807505531
  physical_lateral_drift_m: 0.0002774959679905805
  terminal_arm_joints_rad: [-0.00025046805641095214, 0.4631330095326603, 0.21318348538670218, 0.8649578444936947, 0.0005864330989807919]
  terminal_q6_rad: -0.04850881987104013
  terminal_cup_position_m: [0.019999966759697226, -0.27918465037865553, 0.166881342541034]
  terminal_contact_counts: [1, 1]
  terminal_other_contact_geoms: []
  terminal_maximum_normal_force_n: 0.5923504518570867
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The exact local first 2 mm arm target executes with negligible plan-to-execute drift and produces a measured 1.963 mm physical cup lift.
  - The cup clears table support, remains within 0.278 mm lateral drift, and retains bilateral contact without increasing preload beyond the approximately 0.50 N comparison level.
  - This directly isolates noslip_iterations=10 as the effective fix relative to EXP-097, where the same force scale slipped and produced only approximately 1 micrometre of lift.
  - The attached object exists only in MoveIt Planning Scene; MuJoCo remains constraint-free with no object qpos/qvel write, weld, equality, adhesion, mocap, or teleport.
evidence:
  lift_log_sha256: 629d4fc33096984981b9acd21eef1c58547dabf867b4a025f8418b6448dafdc8
  lift_json_sha256: 149ca2906dd26d555978680d15403e7179847725a5547d41bd06bf5f7412681d
  lift_script_sha256: f2afbdd44ac92907812ce617c35c234857a9a3f576d0b7557cf33650721d77d1
decision: Preserve exact live lifted state and separately preregister a ten-second no-action physical hold before formal LIFT/transport.
```

## Checkpoint CP-137

```yaml
checkpoint_id: CP-137
checkpoint_time: 2026-08-12T03:45:30+08:00
last_valid_experiment: EXP-102
current_hypothesis: The Noslip-supported physical grasp remains off-table with bilateral contact for ten seconds without any command or hidden constraint.
working_tree_status: Same intentional noslip source/test/model/plan/ledger/fork state; protected Gazebo tracked status remains empty. Noslip stack is epoch 0 unpaused at the successful 1.963 mm lifted state.
confirmed_conclusions:
  - ResetWorld, staged approach, contact preload, Planning Scene shadow, and the physical micro-lift all pass on the exact noslip runtime.
  - A time-only observation now isolates stability before increasing lift distance or starting transport.
next_command: Preregister EXP-103 and observe ten continuous seconds with cup drift, drop, support, bilateral contact, force, arm, q6, session, epoch, and no-action gates.
```

## Experiment EXP-103

```yaml
experiment_id: EXP-103
prior_experiment: EXP-102 VALID physical micro-lift
status: RUNNING
lifecycle: NOSLIP_TEN_SECOND_CONSTRAINT_FREE_PHYSICAL_HOLD
run_mode: observe_exact_EXP102_terminal_state_without_action
hypothesis: The lifted cup remains off-table with bilateral contact for ten seconds, with at most 1 mm total drift and at most 0.5 mm drop.
single_variable: Elapsed observation time only. No arm, gripper, Planning Scene, simulator, model, policy, pause, reset, or object-state command is issued.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00025046805641095214, 0.4631330095326603, 0.21318348538670218, 0.8649578444936947, 0.0005864330989807919]
  initial_q6_rad: -0.04850881987104013
  initial_cup_position_m: [0.019999966759697226, -0.27918465037865553, 0.166881342541034]
  hold_script: [/tmp/so101_exp103_hold.py, cf69c47de82e7b84bbf77ec1d4387768961c7a84a0ef4f4cf6ff2ab27e03215b]
  hold_duration_s: 10.0
  maximum_cup_drift_m: 0.001
  maximum_cup_drop_m: 0.0005
  maximum_arm_error_rad: 0.01
  maximum_q6_error_rad: 0.002
  maximum_force_n: 11.60
preconditions:
  - Same process/session/epoch is unpaused with active controllers and physical state matching CP-137.
  - Cup is off-table with bilateral contact and the Planning Scene shadow remains attached; no MuJoCo constraint or attachment exists.
  - Script is observation-only, lint-clean, and SHA-matched; no action occurred after the frozen state.
success_criteria:
  - Every fresh sample for ten seconds remains unpaused at epoch 0, off-table, bilateral, below force ceiling, within arm/q6 bounds, at most 1 mm from initial cup position, and at most 0.5 mm below initial Z.
  - No command, pause/reset, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any freshness, support, contact, force, cup, arm, q6, session, epoch, or duration gate violation fails the run.
invalid_criteria: Any unrecorded physical action or harness/model change invalidates the run.
evidence_root: /tmp/so101-task13-noslip
runtime_start:
  time: 2026-08-12T03:46:05+08:00
  precondition_readback: Fresh lifted state matches CP-137 and script SHA cf69c47d; this transition occurs before the observation window.
decision: PENDING.
next_experiment: Formal LIFT waypoint only after VALID ten-second hold.
```

## Experiment EXP-103 Terminal Result

```yaml
experiment_id: EXP-103
status: VALID
terminal_result: TEN_SECOND_CONSTRAINT_FREE_PHYSICAL_HOLD_PROVED
terminal_time: 2026-08-12T03:46:55+08:00
command: python3 /tmp/so101_exp103_hold.py
exit_code: 0
result:
  hold_duration_s: 10.0
  sample_count: 835
  initial_cup_position_m: [0.01999997789335019, -0.2791846503268693, 0.1668780861227786]
  terminal_cup_position_m: [0.019999973720013813, -0.2791846503491892, 0.16687805834593536]
  maximum_cup_drift_m: 0.00000002808861433396681
  maximum_normal_force_n: 0.5737835676536662
  terminal_table_contact: false
  terminal_bilateral_contact: true
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - Every fresh sample for ten continuous seconds remains bilateral, off-table, within cup/arm/q6/force bounds, and on the same session/epoch.
  - Maximum measured cup drift is approximately 28 nanometres, demonstrating that the physical hold no longer exhibits the prior slow tangential creep.
  - The run sent no action and used no simulator constraint, object write, pause, reset, or hidden aid.
evidence:
  hold_log_sha256: 91bef9272aa031e92a90426567cd50a9e956f254400de0c68a3bf7418bcb78d3
  hold_json_sha256: 29bb8d5b31341e294e2ec1222440944a7816b6eb491884de00665c37d95b4b93
  hold_script_sha256: cf69c47de82e7b84bbf77ec1d4387768961c7a84a0ef4f4cf6ff2ab27e03215b
decision: Preserve exact live state and separately preregister only the first formal LIFT waypoint.
```

## Checkpoint CP-138

```yaml
checkpoint_id: CP-138
checkpoint_time: 2026-08-12T03:47:30+08:00
last_valid_experiment: EXP-103
current_hypothesis: The stable physical grasp will carry the cup from the micro-lift endpoint to the first formal LIFT waypoint with bounded displacement and continuous bilateral contact.
working_tree_status: Same intentional noslip source/test/model/plan/ledger/fork state; protected Gazebo tracked status remains empty. Noslip stack remains epoch 0 unpaused at the stable micro-lift endpoint with Planning Scene shadow attached.
confirmed_conclusions:
  - The contact model now passes both transient physical lift and ten-second static stability.
  - The next action uses the unchanged first waypoint from the formal LIFT policy and does not yet start lateral transport.
next_command: Preregister EXP-104 and execute only formal LIFT waypoint 1 with MoveIt/controller, bilateral, force, support, cup displacement, drift, session, and epoch gates.
```

## Experiment EXP-104

```yaml
experiment_id: EXP-104
prior_experiment: EXP-103 VALID ten-second hold
status: RUNNING
lifecycle: NOSLIP_FORMAL_LIFT_WAYPOINT_1
run_mode: continue_exact_EXP103_terminal_state
hypothesis: The unchanged first LIFT policy waypoint transfers the cup at least 5 mm upward while retaining bilateral physical contact and staying within 30 mm lateral displacement.
single_variable: Execute only LIFT waypoint 1. q6, model, policy, scene, controllers, Planning Scene shadow, session, epoch, and no-attachment physical contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00025046805641095214, 0.4631330095326603, 0.21318348538670218, 0.8649578444936947, 0.0005864330989807919]
  initial_q6_rad: -0.04850881987104013
  initial_cup_position_m: [0.019999973720013813, -0.2791846503491892, 0.16687805834593536]
  lift_target_arm_rad: [-0.000284124852, 0.381814591288, 0.272246878070, 0.916741182602, -0.000291565154]
  lift_script: [/tmp/so101_exp104_policy_lift_waypoint1.py, e95e515b23c505eabc91e944fcc6a16afb1d839a804a90f4aee207c1e4822f04]
  minimum_physical_lift_m: 0.005
  maximum_physical_lift_m: 0.10
  maximum_lateral_displacement_m: 0.03
  maximum_force_n: 11.60
preconditions:
  - Same process/session/epoch is unpaused with active controllers, arm/q6/cup and stable bilateral state matching CP-138.
  - Planning Scene shadow readback remains attached; MuJoCo has no constraint or attachment.
  - Script is lint-clean and SHA-matched; no action occurred after the frozen state.
success_criteria:
  - Plan-to-execute drift is at most 0.01 rad and arm reaches the frozen waypoint.
  - Cup rises 5-100 mm with at most 30 mm lateral displacement, stays off-table, retains bilateral contact through execution and 0.30-second hold, and remains below 11.60 N.
  - Session/epoch and q6 remain unchanged; no pause/reset, simulator constraint/attachment, object write, or hidden aid occurs.
failure_criteria: Any planning, execution, lift, displacement, support, bilateral, force, q6, freshness, provenance, or evidence violation stops before waypoint 2.
invalid_criteria: Any unrecorded state/script/model/policy change or physical attachment aid invalidates the run.
evidence_root: /tmp/so101-task13-noslip
runtime_start:
  time: 2026-08-12T03:48:07+08:00
  precondition_readback: Fresh lifted state matches CP-138; script SHA is e95e515b and this transition occurs before arm planning.
decision: PENDING.
next_experiment: Remaining formal LIFT waypoints only after VALID waypoint-1 transfer.
```

## Experiment EXP-104 Terminal Result

```yaml
experiment_id: EXP-104
status: VALID
terminal_result: FORMAL_LIFT_WAYPOINT_1_PHYSICAL_TRANSFER_PROVED
terminal_time: 2026-08-12T03:49:00+08:00
command: python3 /tmp/so101_exp104_policy_lift_waypoint1.py
exit_code: 0
result:
  lift_trajectory_points: 13
  plan_to_execute_drift_rad: 2.2383872533282556e-10
  physical_vertical_transfer_m: 0.008092936466791406
  physical_lateral_displacement_m: 0.010607720271600073
  terminal_arm_joints_rad: [-0.00023606226902096316, 0.382434587128191, 0.27246225531535007, 0.9166189947303022, -0.0002636111219559103]
  terminal_q6_rad: -0.04851054636613029
  terminal_cup_position_m: [0.01999510358025458, -0.2685769318260159, 0.17497068901080073]
  terminal_contact_counts: [3, 1]
  terminal_other_contact_geoms: []
  terminal_maximum_normal_force_n: 0.7962113299935292
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The first unchanged formal LIFT waypoint physically transfers the cup upward 8.09 mm and laterally 10.61 mm with continuous bilateral contact.
  - The cup remains off-table, force stays below the ceiling, and the MoveIt/controller endpoint converges without changing q6 or provenance.
evidence:
  lift_log_sha256: e6ce64946f1a69d8f2168eff60c6d18539e3f33b89e428ba6481e1da966fc092
  lift_json_sha256: 09a14c5609ba4ec450f0d8216c69847889a638ba3fc0ec1140a6e18415247fd2
  lift_script_sha256: e95e515b23c505eabc91e944fcc6a16afb1d839a804a90f4aee207c1e4822f04
decision: Preserve exact live state and execute the remaining four formal LIFT waypoints as one bounded, waypoint-visible experiment.
```

## Checkpoint CP-139

```yaml
checkpoint_id: CP-139
checkpoint_time: 2026-08-12T03:50:45+08:00
last_valid_experiment: EXP-104
current_hypothesis: The stable Noslip grasp will traverse the remaining four vertical LIFT waypoints and reach the safe-height endpoint without support/contact/force failure.
working_tree_status: Same intentional noslip source/test/model/plan/ledger/fork state; protected Gazebo tracked status remains empty. Noslip stack remains epoch 0 unpaused at formal LIFT waypoint 1.
confirmed_conclusions:
  - The first policy-scale motion succeeds physically, so remaining LIFT can retain unchanged policy waypoints and velocity/acceleration scaling.
  - Each remaining waypoint will be separately planned, executed, endpoint-checked, and recorded inside one fail-fast experiment.
next_command: Preregister EXP-105 and execute LIFT waypoints 2 through 5 with per-waypoint evidence and cumulative transfer gates.
```

## Experiment EXP-105

```yaml
experiment_id: EXP-105
prior_experiment: EXP-104 VALID formal LIFT waypoint 1
status: RUNNING
lifecycle: NOSLIP_REMAINING_FORMAL_LIFT
run_mode: execute_LIFT_waypoints_2_through_5_sequentially
hypothesis: The remaining four unchanged LIFT waypoints raise the cup another 30-80 mm, keep total lateral displacement within 30 mm, and retain bilateral off-table contact.
single_variable: Execute only formal LIFT waypoints 2-5 in order. q6, model, policy, Planning Scene shadow, controllers, session, epoch, and physical contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00023606226902096316, 0.382434587128191, 0.27246225531535007, 0.9166189947303022, -0.0002636111219559103]
  initial_q6_rad: -0.04851054636613029
  initial_cup_position_m: [0.01999510358025458, -0.2685769318260159, 0.17497068901080073]
  lift_targets_arm_rad:
    - [-0.000283936540, 0.312943337339, 0.250048785615, 1.007810530006, -0.000291376841]
    - [-0.000283745683, 0.253568199427, 0.213237198063, 1.103997256470, -0.000291185985]
    - [-0.000276912349, 0.287984861834, 0.150788067636, 1.132029723496, -0.000284352650]
    - [-0.000282114209, 0.200965792445, 0.129655454807, 1.240181404713, -0.000289555209]
  lift_script: [/tmp/so101_exp105_remaining_lift.py, bda8478f308ff8110db41dba4dcb3d4599f9fa6833c85a4a3d8417abf436c1b6]
  maximum_segment_cup_displacement_m: 0.05
  total_vertical_transfer_gate_m: [0.03, 0.08]
  maximum_total_lateral_displacement_m: 0.03
  maximum_force_n: 11.60
preconditions:
  - Same process/session/epoch is unpaused with active controllers and physical state matching CP-139.
  - Planning Scene shadow remains attached and MuJoCo remains constraint-free.
  - Script is lint-clean and SHA-matched; no action occurred after the frozen state.
success_criteria:
  - Every waypoint plans with drift at most 0.01 rad, executes, converges, remains bilateral/off-table/below force ceiling, and moves the cup at most 50 mm in that segment.
  - Final cup rises another 30-80 mm with at most 30 mm cumulative lateral displacement; q6/session/epoch stay unchanged and no hidden aid occurs.
failure_criteria: Any waypoint planning, execution, convergence, contact, support, force, displacement, q6, session, epoch, freshness, or evidence gate stops before the next waypoint.
invalid_criteria: Any unrecorded state/script/model/policy change or physical attachment aid invalidates the run.
evidence_root: /tmp/so101-task13-noslip
runtime_start:
  time: 2026-08-12T03:51:19+08:00
  precondition_readback: Fresh waypoint-1 state matches CP-139; script SHA is bda8478f and this transition occurs before planning waypoint 2.
decision: PENDING.
next_experiment: MOVE_ABOVE_PLACE transport only after VALID remaining LIFT.
```

## Experiment EXP-105 Terminal Result

```yaml
experiment_id: EXP-105
status: VALID
terminal_result: REMAINING_FORMAL_LIFT_PROVED
terminal_time: 2026-08-12T03:52:18+08:00
command: python3 /tmp/so101_exp105_remaining_lift.py
exit_code: 0
result:
  completed_waypoints: 4
  total_vertical_transfer_m: 0.04974549584433274
  total_lateral_displacement_m: 0.0010460641306876228
  terminal_arm_joints_rad: [-0.00031950472111697334, 0.2015600757345103, 0.1299877504869264, 1.2401457978939827, -0.00027049232842978966]
  terminal_q6_rad: -0.048510207270894154
  terminal_cup_position_m: [0.020012970677363965, -0.2696186499109569, 0.22471132092194765]
  terminal_table_contact: false
  terminal_bilateral_contact: true
  terminal_maximum_normal_force_n: 0.7984102689042978
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - All four remaining LIFT waypoints plan, execute, converge, and preserve bilateral off-table physical carry.
  - The cup rises another 49.75 mm with only 1.05 mm cumulative lateral displacement, completing the formal safe-height LIFT phase.
evidence:
  lift_log_sha256: 6630c1800b35f73bf6a270b2d5c3e75350a6009a5ead7e49723307ebde73ab9d
  lift_json_sha256: b5a98186bdb9aafb38f9cff5551cf810065be4bd3efb0a69ec768b78c260e709
  lift_script_sha256: bda8478f308ff8110db41dba4dcb3d4599f9fa6833c85a4a3d8417abf436c1b6
decision: Preserve exact safe-height state and separately preregister the five formal MOVE_ABOVE_PLACE transport waypoints.
```

## Checkpoint CP-140

```yaml
checkpoint_id: CP-140
checkpoint_time: 2026-08-12T03:53:00+08:00
last_valid_experiment: EXP-105
current_hypothesis: The stable safe-height grasp will follow the formal five-waypoint lateral transport to above the red target region without slip or loss of contact.
working_tree_status: Same intentional noslip source/test/model/plan/ledger/fork state; protected Gazebo tracked status remains empty. Noslip stack remains epoch 0 unpaused at final LIFT waypoint with Planning Scene shadow attached.
confirmed_conclusions:
  - Formal LIFT is physically complete and stable.
  - MOVE_ABOVE_PLACE expected TCP travel is approximately 95 mm laterally with only a few millimetres vertical change, so transport gates are separated from lift gates.
next_command: Preregister EXP-106 and execute all five MOVE_ABOVE_PLACE waypoints with per-waypoint physical evidence.
```

## Experiment EXP-106

```yaml
experiment_id: EXP-106
prior_experiment: EXP-105 VALID remaining LIFT
status: RUNNING
lifecycle: NOSLIP_FORMAL_MOVE_ABOVE_PLACE
run_mode: execute_five_transport_waypoints_sequentially
hypothesis: The unchanged MOVE_ABOVE_PLACE waypoints carry the cup 60-120 mm laterally with at most 30 mm vertical change and continuous bilateral off-table contact.
single_variable: Execute only formal MOVE_ABOVE_PLACE waypoints 1-5. q6, model, policy, Planning Scene shadow, controllers, session, epoch, and physical contract remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [-0.00031950472111697334, 0.2015600757345103, 0.1299877504869264, 1.2401457978939827, -0.00027049232842978966]
  initial_q6_rad: -0.048510207270894154
  initial_cup_position_m: [0.020012970677363965, -0.2696186499109569, 0.22471132092194765]
  transport_targets_arm_rad:
    - [0.078649232242, 0.202916192985, 0.125650124859, 1.227082691882, 0.000085728349]
    - [0.157580578693, 0.204866593526, 0.121644794912, 1.213983979051, 0.000461011907]
    - [0.236511925143, 0.206816994066, 0.117639464964, 1.200885266221, 0.000836295464]
    - [0.315443271594, 0.208767394607, 0.113634135017, 1.187786553390, 0.001211579022]
    - [0.394374618045, 0.210717795147, 0.109628805069, 1.174687840559, 0.001586862580]
  transport_script: [/tmp/so101_exp106_transport.py, 0d87f8b7a0a7362dba13a83ce2cf0f71fe316a3c84a27e7e4af83704a4906c81]
  maximum_segment_cup_displacement_m: 0.04
  total_lateral_displacement_gate_m: [0.06, 0.12]
  maximum_total_vertical_change_m: 0.03
  maximum_force_n: 11.60
preconditions:
  - Same process/session/epoch is unpaused with active controllers and physical state matching CP-140.
  - Planning Scene shadow remains attached and MuJoCo remains constraint-free.
  - Script is lint-clean and SHA-matched; no action occurred after the frozen state.
success_criteria:
  - Every waypoint plans with drift at most 0.01 rad, executes, converges, remains bilateral/off-table/below force ceiling, and moves the cup at most 40 mm in that segment.
  - Final cup moves 60-120 mm laterally with at most 30 mm total vertical change; q6/session/epoch stay unchanged and no hidden aid occurs.
failure_criteria: Any waypoint planning, execution, convergence, contact, support, force, displacement, q6, session, epoch, freshness, or evidence gate stops before the next waypoint.
invalid_criteria: Any unrecorded state/script/model/policy change or physical attachment aid invalidates the run.
evidence_root: /tmp/so101-task13-noslip
runtime_start:
  time: 2026-08-12T03:53:33+08:00
  precondition_readback: Fresh final-LIFT state matches CP-140; script SHA is 0d87f8b7 and this transition occurs before transport waypoint 1.
decision: PENDING.
next_experiment: DESCEND_TO_PLACE only after VALID transport.
```

## Experiment EXP-106 Terminal Result

```yaml
experiment_id: EXP-106
status: VALID
terminal_result: BEHAVIORAL_FAILURE_MOVEIT_EXECUTION_MONITOR_ABORTED
terminal_time: 2026-08-12T03:54:24+08:00
command: python3 /tmp/so101_exp106_transport.py
exit_code: 1
result:
  completed_recorded_waypoints: 4
  controller_reached_waypoint_5: true
  terminal_arm_joints_rad: [0.3941807984901571, 0.21134367594946993, 0.11009181694930642, 1.1746502503950658, 0.0017901430972551884]
  terminal_q6_rad: -0.048090900762462946
  terminal_cup_position_m: [-0.07798912725454922, -0.2642760937716864, 0.22856713117290245]
  terminal_cup_orientation_xyzw: [-0.0165062991, 0.0018002683, -0.1655964131, 0.9860538165]
  terminal_contact_counts: [3, 4]
  terminal_other_contact_geoms: []
  terminal_maximum_normal_force_n: 2.8177
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - Waypoints 1-4 completed with bilateral off-table physical carry; at waypoint 5 the monitor observed one transient non-bilateral sample and cancelled the MoveIt goal.
  - Fresh post-cancel readback proves the controller nevertheless reached waypoint 5 and the cup remains stably grasped off-table above the target region.
  - The zero-duration contact monitor is too sensitive to convex-mesh contact-point transitions. This is an execution-observer defect, not proof of a physical grasp failure.
  - Because the registered success contract required every waypoint execution to report success, EXP-106 is retained as a VALID behavioral failure and cannot count toward final acceptance.
evidence:
  transport_log_sha256: 46f7c042020694bbd541b68e3844eedaa3eee37ea67906bff3ca5bd6949da817
  transport_json_sha256: 3a32648ae9201096378694a6b8f429248e7e8fe7ef2892bc6852d5ad673a3697
  transport_script_sha256: 0d87f8b7a0a7362dba13a83ce2cf0f71fe316a3c84a27e7e4af83704a4906c81
decision: Add a bounded 50 ms bilateral-contact loss grace to the execution observer, first validate the preserved endpoint with an observation-only window, then continue descent. A fresh full reset-to-release cycle remains mandatory for acceptance.
```

## Checkpoint CP-141

```yaml
checkpoint_id: CP-141
checkpoint_time: 2026-08-12T03:57:40+08:00
last_valid_experiment: EXP-106 VALID behavioral failure
current_hypothesis: The waypoint-5 endpoint is physically stable; a 50 ms grace will reject sustained loss while avoiding cancellation on one transient contact-point handoff.
working_tree_status: Same intentional noslip source/test/model/plan/ledger/fork state; protected Gazebo tracked status remains empty. Session so101-task13-noslip remains epoch 0 unpaused at the final MOVE_ABOVE_PLACE endpoint.
confirmed_conclusions:
  - The cup physically traversed the entire transport path and is above the target region.
  - No physics pause, reset, object state write, simulator constraint, or hidden attachment occurred.
  - EXP-106 does not satisfy the success contract and forces a later clean full-cycle rerun.
next_command: Preregister and run an observation-only endpoint stability window before any descent.
```

## Experiment EXP-107

```yaml
experiment_id: EXP-107
prior_experiment: EXP-106 VALID behavioral failure
status: RUNNING
lifecycle: NOSLIP_TRANSPORT_ENDPOINT_STABILITY_READBACK
run_mode: observation_only_no_motion
hypothesis: The preserved waypoint-5 endpoint remains bilateral, off-table, below force ceiling, and position-stable for at least 2 seconds without any command.
single_variable: Observe the unchanged live state only. No planning, controller goal, gripper command, reset, pause, Planning Scene mutation, or model/source change is permitted.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  expected_arm_joints_rad: [0.3941807984901571, 0.21134367594946993, 0.11009181694930642, 1.1746502503950658, 0.0017901430972551884]
  expected_q6_rad: -0.048090900762462946
  expected_cup_position_m: [-0.07798912725454922, -0.2642760937716864, 0.22856713117290245]
  observation_duration_s: 2.0
  maximum_cup_position_drift_m: 0.0005
  maximum_force_n: 11.60
preconditions:
  - Controllers remain active; the exact session/epoch is unpaused and matches CP-141.
  - Planning Scene shadow remains attached and MuJoCo remains constraint-free.
success_criteria:
  - Every fresh sample is epoch 0, unpaused, bilateral, off-table, below 11.60 N, and total cup position drift is at most 0.5 mm over at least 2 seconds.
failure_criteria: Any stale evidence, provenance change, support contact, sustained or transient non-bilateral sample, force breach, or excessive drift is a behavioral failure.
invalid_criteria: Any motion or state mutation during the window invalidates the run.
evidence_root: /tmp/so101-task13-noslip
decision: PENDING.
next_experiment: Implement/test the 50 ms execution-monitor grace and preregister DESCEND_TO_PLACE only after VALID stability.
```

## Experiment EXP-107 Terminal Result

```yaml
experiment_id: EXP-107
status: VALID
terminal_result: TRANSPORT_ENDPOINT_STABLE
terminal_time: 2026-08-12T03:59:28+08:00
command: python3 /tmp/so101_exp107_observe.py
exit_code: 0
result:
  observation_duration_s: 2.0038569410025957
  fresh_sample_count: 167
  maximum_cup_position_drift_m: 4.6659496498187894e-09
  terminal_cup_position_m: [-0.07798644503551211, -0.2642695347918186, 0.2285615847719923]
  terminal_contact_counts: [3, 4]
  terminal_other_contact_geoms: []
  terminal_maximum_normal_force_n: 2.8207965652082163
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - The waypoint-5 endpoint is physically stable over 167 consecutive fresh samples with only 4.7 nm observed position drift.
  - Bilateral contact, off-table state, force ceiling, epoch, and unpaused provenance remain valid throughout the no-motion window.
  - This isolates EXP-106 to a transient execution-monitor sample rather than a persistent physical contact loss.
evidence:
  observe_log_sha256: 4d26880f5bc01b5e22da37b1e058b6e504648ea34c0bca33d027169d250dff3d
  observe_json_sha256: 9dd09da6c876399825f860ab0b710b2b084e2490a71b20d5806e8a18dfdf0942
  observe_script_sha256: e94fae1593912c9b2c9a5a7cc0eed3355eae2abdb25be5907399d8fec44005ec
decision: Keep the physical state unchanged, land the tested SustainedConditionGuard contract, and execute formal DESCEND_TO_PLACE with a 50 ms bilateral-contact loss grace.
```

## Checkpoint CP-142

```yaml
checkpoint_id: CP-142
checkpoint_time: 2026-08-12T04:01:00+08:00
last_valid_experiment: EXP-107
current_hypothesis: The three formal descent waypoints will place the cup on the table inside the red target region while the bounded monitor rejects only sustained bilateral loss.
working_tree_status: Same intentional source/model/plan/ledger/fork state plus tested SustainedConditionGuard source and unit tests. Protected Gazebo tracked status remains empty; session remains epoch 0 unpaused at transport endpoint.
confirmed_conclusions:
  - SustainedConditionGuard unit contract is RED then GREEN: shorter than 50 ms recovers, 50 ms sustained loss raises, invalid negative grace is rejected.
  - The guard applies only to bilateral-contact continuity; stale evidence, pause/reset, force breach, and premature table contact remain immediate aborts.
next_command: Preregister EXP-108 and execute only the three formal DESCEND_TO_PLACE waypoints.
```

## Experiment EXP-108

```yaml
experiment_id: EXP-108
prior_experiment: EXP-107 VALID endpoint stability
status: RUNNING
lifecycle: NOSLIP_FORMAL_DESCEND_TO_PLACE
run_mode: execute_three_descend_waypoints_sequentially
hypothesis: The unchanged DESCEND_TO_PLACE waypoints lower the cup 40-90 mm onto table support within the red target region while preserving bilateral contact and force safety.
single_variable: Execute only formal DESCEND_TO_PLACE waypoints 1-3 with the tested 50 ms bilateral-contact-loss grace. q6, model, physics, policy waypoints, Planning Scene shadow, controllers, session, and epoch remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [0.3941807984901571, 0.21134367594946993, 0.11009181694930642, 1.1746502503950658, 0.0017901430972551884]
  initial_q6_rad: -0.048090900762462946
  initial_cup_position_m: [-0.07798644503551211, -0.2642695347918186, 0.2285615847719923]
  descend_targets_arm_rad:
    - [0.392478252768, 0.303606814934, 0.110730521878, 1.115206323144, 0.001727851167]
    - [0.390581887491, 0.396495834720, 0.111832238686, 1.055724805729, 0.001868839753]
    - [0.389633705130, 0.442941344113, 0.112383097091, 1.025984047022, 0.001939334047]
  descend_script: [/tmp/so101_exp108_descend.py, 73eec4f7149a8db37d38de3e3717da583a14bda8d6b818a9d0a4c27734a1d3ad]
  bilateral_contact_loss_grace_s: 0.05
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
  total_vertical_descent_gate_m: [0.04, 0.09]
  maximum_total_lateral_displacement_m: 0.03
  maximum_force_n: 11.60
preconditions:
  - Same session/epoch is unpaused, active, attached only in MoveIt Planning Scene, and matches CP-142.
  - Script is Ruff-clean, pycompile-clean, and SHA-matched; no state action occurred after preregistration.
success_criteria:
  - Waypoints 1-2 plan, execute, converge, remain bilateral/off-table/below force ceiling; final waypoint may gain table support and must stabilize bilateral plus supported for 0.20 s.
  - Final cup descends 40-90 mm, moves at most 30 mm laterally, and lies inside the frozen target XY bounds; q6/session/epoch remain unchanged.
failure_criteria: Any planning, handoff, execution, sustained contact-loss, support timing, force, convergence, displacement, target-region, q6, or provenance gate failure stops immediately.
invalid_criteria: Any pause/reset, state write, simulator constraint, unrecorded input change, or hidden physical aid invalidates the run.
evidence_root: /tmp/so101-task13-noslip
decision: PENDING.
next_experiment: RELEASE only after VALID supported descent.
```

## Experiment EXP-108 Terminal Result

```yaml
experiment_id: EXP-108
status: VALID
terminal_result: BEHAVIORAL_FAILURE_INCORRECT_PRE_RELEASE_SUPPORT_GATE
terminal_time: 2026-08-12T04:04:02+08:00
command: python3 /tmp/so101_exp108_descend.py
exit_code: 1
result:
  completed_recorded_waypoints: 2
  controller_reached_waypoint_3: true
  terminal_arm_joints_rad: [0.38957355585773323, 0.4433948955089533, 0.11258928948614937, 1.0259276430255333, 0.0020372554389736976]
  terminal_q6_rad: -0.04807858385022937
  terminal_cup_position_m: [-0.07653212406397943, -0.2611527991773442, 0.18441365797552164]
  terminal_cup_orientation_xyzw: [-0.014502704376037298, 0.0012653019622647238, -0.1765424037415066, 0.9841853739300821]
  terminal_contact_counts: [3, 2]
  terminal_other_contact_geoms: []
  terminal_maximum_normal_force_n: 4.777083790809136
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - All three formal DESCEND_TO_PLACE waypoints physically executed and converged; the script then timed out because it incorrectly required table support before opening the gripper.
  - The protected Gazebo production lifecycle deliberately ends DESCEND_TO_PLACE at a pre-release clearance and validates against release_alignment_target, equal to place pose plus [0.005, -0.005, 0.014] m settling compensation.
  - The frozen Gazebo-parity release target is [-0.075, -0.255, 0.179] m. The live cup errors are [0.001532, 0.006153, -0.005414] m, within the formal 10 mm XY and 10 mm Z pre-release tolerances.
  - Therefore this is a VALID test-harness failure, not a physical descent failure. It cannot count as final acceptance, but the preserved physical state is eligible for the formal OPEN_GRIPPER transition.
evidence:
  descend_log_sha256: 58321ac3413f23b32139bde3ca738119b8c7a0ea74bb14e006f67b88e6cc8e4e
  descend_json_sha256: 3686bb630d8abd9992021d10f0e5780fddf2d8fadade0e183ffe0cd4df6bfe38
  descend_script_sha256: 73eec4f7149a8db37d38de3e3717da583a14bda8d6b818a9d0a4c27734a1d3ad
decision: Preserve the live pre-release pose, use the Gazebo-parity compensated release target, then OPEN_GRIPPER, RETREAT, detach/sync the Planning Scene shadow, and evaluate the real post-release cup.
```

## Checkpoint CP-143

```yaml
checkpoint_id: CP-143
checkpoint_time: 2026-08-12T04:09:00+08:00
last_valid_experiment: EXP-108 VALID behavioral failure
current_hypothesis: Opening q6 at the valid compensated pre-release pose lets the unconstrained cup settle on the table, after which the formal retreat and Planning Scene detach/sync yield a stable final placement.
working_tree_status: Same intentional source/model/plan/ledger/fork state plus SustainedConditionGuard. Protected Gazebo tracked status remains empty; session remains epoch 0 unpaused at formal DESCEND_TO_PLACE endpoint.
confirmed_conclusions:
  - MuJoCo and Gazebo share the same formal pre-release clearance semantics; table support is a post-open outcome, not a pre-open requirement.
  - No additional downward arm motion is authorized or necessary at this checkpoint.
  - The diagnostic cycle remains non-accepting because EXP-106 and EXP-108 had valid behavioral failures; a later clean full rerun is mandatory.
next_command: Preregister EXP-109 and execute OPEN_GRIPPER plus formal RETREAT, Planning Scene detach/sync, and final physical outcome evaluation.
```

## Experiment EXP-109

```yaml
experiment_id: EXP-109
prior_experiment: EXP-108 VALID behavioral failure at physically valid pre-release pose
status: RUNNING
lifecycle: NOSLIP_RELEASE_RETREAT_FINAL_OUTCOME_DIAGNOSTIC
run_mode: open_gripper_then_three_retreat_waypoints_then_detach_sync_and_evaluate
hypothesis: The unconstrained cup settles from the Gazebo-parity pre-release clearance into the target region, stays supported while the arm retreats, and passes the frozen final-placement evaluator after Planning Scene detach/sync.
single_variable: Execute only the formal OPEN_GRIPPER, RETREAT, DETACH_MOVEIT/SYNC_WORLD_OBJECT, and final outcome transitions. No model, physics, arm waypoint, target, evaluator, session, or epoch change is permitted.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [0.38957355585773323, 0.4433948955089533, 0.11258928948614937, 1.0259276430255333, 0.0020372554389736976]
  initial_q6_rad: -0.04807858385022937
  initial_cup_position_m: [-0.07653212406397943, -0.2611527991773442, 0.18441365797552164]
  release_target_xyz_m: [-0.075, -0.255, 0.179]
  pre_release_xy_tolerance_m: 0.010
  pre_release_z_tolerance_m: 0.010
  release_q6_rad: 0.750
  retreat_targets_arm_rad:
    - [0.390581887491, 0.396495834720, 0.111832238686, 1.055724805729, 0.001868839753]
    - [0.392478252768, 0.303606814934, 0.110730521878, 1.115206323144, 0.001727851167]
    - [0.394374618045, 0.210717795147, 0.109628805069, 1.174687840559, 0.001586862580]
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
  final_support_height_range_m: [0.155, 0.175]
  release_script: [/tmp/so101_exp109_release_retreat.py, 278414996f9e1242c74d7bb02ff33d227d50e2a8c35f7dc96ecad2147259dbae]
  maximum_force_n: 11.60
preconditions:
  - Same unpaused epoch-0 session, active controllers, bilateral off-table grasp, and exact physical state match CP-143.
  - Planning Scene plastic_cup remains attached only as a collision shadow; MuJoCo remains constraint-free.
  - Script is Ruff-clean, pycompile-clean, and SHA-matched; no state action occurred after preregistration.
success_criteria:
  - OPEN_GRIPPER reaches q6 0.750; the cup becomes gripper-contact-free and table-supported for at least 0.20 s.
  - Three formal RETREAT waypoints plan, execute, and converge while the real cup remains supported and is never re-contacted.
  - Planning Scene readback contains a 13-primitive world plastic_cup and no attached plastic_cup at the observed pose.
  - At least five post-release samples spanning 0.20 s pass target region, height, upright, stillness, support, detach, controller, safety, and shadow gates.
failure_criteria: Any release, settling, planning, execution, support, re-contact, force, detach/sync, final placement, or provenance gate failure stops immediately.
invalid_criteria: Any pause/reset, object state write, simulator constraint, hidden attachment, unrecorded input change, or evidence discontinuity invalidates the run.
evidence_root: /tmp/so101-task13-noslip
decision: PENDING.
next_experiment: Clean ResetWorld and full production rerun regardless of diagnostic result.
```

## Experiment EXP-109 Terminal Result

```yaml
experiment_id: EXP-109
status: VALID
terminal_result: BEHAVIORAL_FAILURE_RESIDUAL_FIXED_PAD_CONTACT_GATE
terminal_time: 2026-08-12T04:11:15+08:00
command: python3 /tmp/so101_exp109_release_retreat.py
exit_code: 1
result:
  release_command_completed: true
  retreat_waypoints_executed: 0
  terminal_arm_joints_rad: [0.38959016995746437, 0.4434564518190401, 0.11270955937314296, 1.0259245490073445, 0.0020365678671788972]
  terminal_q6_rad: 0.7499563770835956
  terminal_cup_position_m: [-0.07681417919303282, -0.26186788592522575, 0.1659757806194288]
  terminal_cup_orientation_xyzw: [-0.014497102330612213, 0.0012573369792875288, -0.17660340233720787, 0.9841745228416847]
  terminal_table_contact: true
  terminal_contact_counts: [2, 0]
  terminal_maximum_normal_force_n: 0.13408595319523298
  residual_fixed_pad_force_n: 0.018556938760667562
  terminal_reset_epoch: 0
  terminal_paused: false
diagnosis:
  - q6 reached the frozen 0.750 release target and the unconstrained cup fell onto the table at the correct upright support height.
  - The moving jaw has zero contact, but the fixed fingertip remains in a near-zero 0.0186 N grazing contact until arm retreat begins.
  - The script incorrectly required zero contact from both fingers before RETREAT. The protected Gazebo lifecycle allows this residual fixed-pad contact and removes it with immediate retreat before final outcome evaluation.
  - No arm retreat or Planning Scene detach occurred, so the live state is safely recoverable by the next registered continuation.
evidence:
  release_log_sha256: ca14253598262443c7ab924a626f19d2b3fec5b8df1c3ec97914a8d878888080
  release_json_sha256: ea8c562cd280c95cc104ccd83814725aa5702edd7622e1f49503dc4652f65a45
  release_script_sha256: 278414996f9e1242c74d7bb02ff33d227d50e2a8c35f7dc96ecad2147259dbae
decision: Preserve the supported cup and open gripper; continue the formal immediate RETREAT while allowing only the observed sub-1 N fixed-pad residual, then require zero gripper contact at each endpoint.
```

## Checkpoint CP-144

```yaml
checkpoint_id: CP-144
checkpoint_time: 2026-08-12T04:13:00+08:00
last_valid_experiment: EXP-109 VALID behavioral failure
current_hypothesis: The first retreat waypoint clears the residual fixed-pad grazing contact without disturbing the supported cup; remaining retreat, detach/sync, and final evaluation then complete normally.
working_tree_status: Same intentional source/model/plan/ledger/fork state. Protected Gazebo tracked status remains empty; session is epoch 0 unpaused with q6 open, cup table-supported, and Planning Scene shadow still attached.
confirmed_conclusions:
  - Physical release succeeded without simulator attachment or object state mutation.
  - Residual contact is only on the fixed side, at 0.0186 N, while the moving jaw is clear.
  - Final target membership remains unknown and will be judged only after retreat and settling; this diagnostic cycle still cannot count as final acceptance.
next_command: Preregister EXP-110 and execute formal RETREAT, then detach/sync and evaluate.
```

## Experiment EXP-110

```yaml
experiment_id: EXP-110
prior_experiment: EXP-109 VALID behavioral failure after completed physical release
status: RUNNING
lifecycle: NOSLIP_RETREAT_DETACH_SYNC_FINAL_OUTCOME_CONTINUATION
run_mode: three_retreat_waypoints_then_detach_sync_and_evaluate
hypothesis: The unchanged RETREAT path clears the residual fixed-pad contact, leaves the cup supported, and permits a correct 13-primitive Planning Scene world sync and final placement evaluation.
single_variable: Continue from the completed OPEN_GRIPPER transition. During motion only, allow the already observed fixed-pad residual while prohibiting moving-jaw contact and any released-cup contact force above 1 N; all endpoints require zero gripper contact.
frozen_inputs:
  simulation_session_id: so101-task13-noslip
  reset_epoch: 0
  initial_arm_joints_rad: [0.38959016995746437, 0.4434564518190401, 0.11270955937314296, 1.0259245490073445, 0.0020365678671788972]
  initial_q6_rad: 0.7499563770835956
  initial_cup_position_m: [-0.07681417919303282, -0.26186788592522575, 0.1659757806194288]
  initial_table_contact: true
  initial_residual_fixed_pad_force_n: 0.018556938760667562
  retreat_targets_arm_rad:
    - [0.390581887491, 0.396495834720, 0.111832238686, 1.055724805729, 0.001868839753]
    - [0.392478252768, 0.303606814934, 0.110730521878, 1.115206323144, 0.001727851167]
    - [0.394374618045, 0.210717795147, 0.109628805069, 1.174687840559, 0.001586862580]
  continuation_script: [/tmp/so101_exp110_retreat_detach.py, cf858df5d23be6ffd583b8bc469dacdb83b4bf679691f6e34ba61e6869c88aae]
  maximum_released_contact_force_during_retreat_n: 1.0
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
  final_support_height_range_m: [0.155, 0.175]
preconditions:
  - Same session/epoch is unpaused; q6 is open; cup is upright and table-supported; moving jaw has no contact; residual fixed contact remains below 1 N.
  - Planning Scene plastic_cup remains attached only as a collision shadow, and MuJoCo remains constraint-free.
  - Script is Ruff-clean, pycompile-clean, and SHA-matched; no state action occurred after preregistration.
success_criteria:
  - All three retreat waypoints plan, execute, converge, and end with stable table support and zero gripper contact; during motion the moving jaw never recontacts and released-cup force stays below 1 N.
  - Planning Scene readback contains a 13-primitive world plastic_cup and no attached plastic_cup at the observed physical pose.
  - Five or more new samples spanning 0.20 s pass the unchanged final-placement evaluator.
failure_criteria: Any planning, execution, support, contact-force, endpoint, detach/sync, final outcome, or provenance gate failure stops immediately.
invalid_criteria: Any pause/reset, object state write, simulator constraint, hidden attachment, unrecorded input change, or evidence discontinuity invalidates the run.
evidence_root: /tmp/so101-task13-noslip
decision: PENDING.
next_experiment: Clean ResetWorld and full production rerun regardless of result.
```

## Experiment EXP-113 Terminal Result

```yaml
experiment_id: EXP-113
status: VALID
terminal_result: BEHAVIORAL_FAILURE_RESET_CLIENT_RETRY_STORM
terminal_time: 2026-08-12T04:31:13+08:00
command: python3 /tmp/so101_exp113_reset.py
exit_code: 1
result:
  reset_service_reported_success: true
  reset_client_terminal_error: ResetFailed reset timeout waiting for authoritative step-zero evidence
  before_reset_epoch: 0
  before_simulation_step: 31748
  before_arm_joint_positions_rad: [0.000021856609761458833, 0.10055151128456585, 0.10039613118161532, 0.20010896297833683, 0.000011508124652193543]
  before_cup_position_m: [0.020000000000000007, -0.28, 0.16480156647042168]
  terminal_controllers_active: false
  terminal_paused: true
follow_up_read_only_diagnosis:
  - One idempotent pause(true) after the failed client returned authoritative reset_epoch=1, simulation_step=0, paused=true, and cup_position=[0.02,-0.28,0.165]. The central MuJoCo reset and support-plugin ABI therefore worked.
  - The failed transaction issued approximately 930 idempotent pause snapshot retries in 10 seconds. Each old-epoch/stale loop synchronously called pause(true), saturating the service and Best-Effort evidence path before the observer could drain the reset snapshot.
  - The live contract test had hidden this production-path difference by wrapping reset_world and pause with an extra drain_feedback interval; the real MujocoResetClient had no bounded drain interval.
evidence:
  reset_json_sha256: 0de55567663b686536fa8332d31a6fd079f4faed9f6161ba1731c53f8c36b16e
  reset_log_sha256: d564134364e9f22a64495d43114656d2a27fa35d36d09dcb300cd402dc9f60ad
  pre_reset_cua_sha256: f3d9e1b697030e3565a217462820abab1feff2f8d3cbabcc44f9b253e979d432
  diagnostic_script_sha256: 5dc85c3a513a9ac13f4afae5e9ec6cff1f7d14bf4d099ab0da09f7908ca04b1d
decision: Preserve this as a valid failure. Fix the production client to drain subscriptions before an at-most-20-Hz idempotent snapshot retry; do not weaken epoch, step-zero, pause, joint, object, controller, scene, or visual acceptance.
```

## Checkpoint CP-148

```yaml
checkpoint_id: CP-148
checkpoint_time: 2026-08-12T04:46:00+08:00
last_valid_experiment: EXP-113 VALID behavioral failure
current_hypothesis: A 50 ms bounded snapshot-retry period permits DDS feedback drain and prevents the service retry storm while retaining an idempotent recovery path for publisher contention.
working_tree_status: Intentional Task 13/14 changes plus the reset-client/test fix. Protected src/so101_gazebo_demo_py tracked status remains empty.
confirmed_conclusions:
  - New regression test failed under the old client with a reset timeout when a pause retry interrupted required subscription drain.
  - Minimal production fix passed that regression test; complete test_mujoco_reset.py is 21/21 passing.
  - so101_mujoco_demo_py was rebuilt into the active fresh overlay without changing the running simulator model or support-plugin binary.
  - Reset source SHA is d0b618416816904b6dce3a4a199adf81c2c52f1574e99cdca4fa57889e38fc7d and test SHA is 5775129b40a95b7ae861a2fd00b165e7bed1208a366d28c2e4800e328390860b.
next_command: Preregister EXP-114, reactivate/resume only as recorded setup, move to task12_safe, capture pre-reset CUA, then run the rebuilt reset client for epoch 1 -> 2.
```

## Experiment EXP-114

```yaml
experiment_id: EXP-114
prior_experiment: EXP-113 VALID reset-client retry-storm failure
status: RUNNING
lifecycle: BOUNDED_DRAIN_RESETWORLD_REQUALIFICATION
run_mode: controlled_recovery_changed_state_then_one_task_start_reset_and_scene_restore
hypothesis: The rebuilt client drains evidence before retrying snapshots, so one ResetWorld(task_start) produces a correlated epoch 1 -> 2 step-zero receipt and restores the full task-start scene.
single_variable: Replace only the reset client's unbounded pause retry storm with a 50 ms bounded retry interval. Physics, model, controller configuration, keyframe, scene geometry, evidence thresholds, and session remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 1
  expected_new_reset_epoch: 2
  keyframe: task_start
  controlled_setup:
    - resume physics from the EXP-113 fail-closed pause
    - reactivate arm_controller and gripper_controller
    - execute the unchanged task12_safe target [0.0, 0.1, 0.1, 0.2, 0.0]
  expected_reset_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_retry_period_s: 0.05
  reset_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py, d0b618416816904b6dce3a4a199adf81c2c52f1574e99cdca4fa57889e38fc7d]
  reset_test: [src/so101_mujoco_demo_py/test/test_mujoco_reset.py, 5775129b40a95b7ae861a2fd00b165e7bed1208a366d28c2e4800e328390860b]
  reset_script: [/tmp/so101_exp114_reset.py, fed04912453c5d29782e404fdaa07697dc462602a376a49f244d498b9841a67c]
preconditions:
  - Same session and simulator process are preserved at authoritative epoch 1 step 0, paused, with the physical task-start state proven by read-only diagnostics.
  - Only the failed transaction's controllers are inactive; controlled setup will restore them before the unchanged changed-state motion.
  - Reset regression test and the entire reset unit file pass; installed Python package contains the new reset client.
success_criteria:
  - Changed-state setup executes successfully and passive CUA proves the arm is not at task_start before reset.
  - Reset receipt is exactly 1 -> 2 at step 0; final evidence is paused, the cup is within 3 mm, all six joints are within 0.002 rad, and both motion controllers are active.
  - Planning Scene readback is exactly table=1, pedestal=1, plastic_cup=13 with expected colors and no attached object.
  - Passive post-reset CUA shows RViz left, Viewer right, horizontal task-start arm, open gripper clear of upright original cup, table, pedestal, target ring, and PAUSE.
failure_criteria: Any setup, reset, epoch, joint, object, controller, scene, or visual mismatch blocks the full pick-place rerun.
invalid_criteria: Any unrecorded state action, process restart, model/config change, direct state write, hidden constraint, or missing CUA evidence invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: One fresh full production pick-place only after EXP-114 is VALID.
```

## Experiment EXP-114 Terminal Result

```yaml
experiment_id: EXP-114
status: VALID
terminal_result: QUALIFIED_RESETWORLD_AND_VISUAL_ACCEPTANCE
terminal_time: 2026-08-12T04:40:00+08:00
command: python3 /tmp/so101_exp114_reset.py
exit_code: 0
result:
  reset_receipt: {old_epoch: 1, new_epoch: 2, simulation_step: 0, keyframe: task_start}
  final_paused: true
  final_cup_position_m: [0.02, -0.28, 0.165]
  final_cup_linear_velocity_m_s: [0.0, 0.0, 0.0]
  final_cup_angular_velocity_rad_s: [0.0, 0.0, 0.0]
  final_joint_positions_rad: [0.000000020106801636346586, 0.0000911352966981906, 0.00008220945026002406, 0.000007552795673726909, 0.000000002240418047689964, -0.0000000607537537969906]
  controllers_active: true
  planning_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_color_ids: [pedestal, plastic_cup, table]
  planning_scene_attached_object_ids: []
visual_acceptance:
  rviz_left_mujoco_right: true
  horizontal_task_start_arm: true
  open_gripper_clear_of_cup: true
  upright_cup_at_original_position: true
  table_pedestal_target_ring_visible: true
  viewer_pause_visible: true
evidence:
  reset_json_sha256: 04ecb3de2e2f391dbae2f77164fd6ed8b71effe4c0a2809cab54887cfa8cd85b
  reset_log_sha256: 17587908681b2e3736d50f6c4848d950804beb257313681d0f8d885fce2d66ff
  changed_state_json_sha256: 4b9dd5e296359531a18b0dbc42094e1e8abe2a00b9ac9fdff52aa80e99ae508a
  changed_state_log_sha256: 61ccf60c962a5ec01b29f5f6578bfa0eaf420610a791318a083c3cdde27c3854
  pre_reset_cua_sha256: 6b4d1e29afbc1662c4fe4a2ae26aa0d21d6c6eaf4f4321e9ef9e827460bbbe93
  post_reset_cua_sha256: 62ec2515fc6f2fb6da862125b96f380749f721ae919964321be15efcb929ddda
decision: ResetWorld is qualified for repeated downstream experiments. Start one fresh full physical pick-place from this epoch-2 paused task_start checkpoint; do not reuse partial EXP-102 through EXP-111 outcomes as success.
```

## Checkpoint CP-149

```yaml
checkpoint_id: CP-149
checkpoint_time: 2026-08-12T04:41:00+08:00
last_valid_experiment: EXP-114 VALID qualified reset
current_hypothesis: The no-slip physical policy plus measured place-settling compensation can complete one uninterrupted staged pick-place from epoch 2.
working_tree_status: Intentional Task 13/14 changes including reset fix; protected src/so101_gazebo_demo_py tracked status remains empty. Simulator is paused at task_start with controllers active and exact formal Planning Scene restored.
confirmed_conclusions:
  - ResetWorld is now an effective, repeatable experiment boundary proven electronically and visually.
  - The prior segmented experiments proved staged approach/contact, low-force physical grasp, micro-lift, lift, transport, descent, release, and retreat independently, but no prior sequence counts as a full-cycle success.
  - Place settling compensation target remains [-0.0788,-0.2475,0.1835] before release so the settled cup can enter the unchanged final target region.
next_command: Freeze and preregister one full-cycle runner that executes the same staged phase contracts without teleport, hidden constraint, object-state write, or unbounded retry.
```

## Experiment EXP-115

```yaml
experiment_id: EXP-115
prior_experiment: EXP-114 VALID qualified reset
status: RUNNING
lifecycle: FULL_PHYSICAL_PICK_PLACE_WITH_CLOSED_LOOP_ALIGNMENT
run_mode: one_uninterrupted_epoch_2_staged_cycle
hypothesis: The independently qualified no-slip phase contracts, followed by bounded closed-loop alignment to the measured MuJoCo pre-release target, complete one physical pick-place with the cup stably inside the unchanged red-ring target.
single_variable: Combine the already qualified phase implementations into one uninterrupted epoch-2 cycle and insert only the tested bounded place-alignment correction before release. No reset, pause, object-state write, simulator constraint, hidden attachment, model/config change, or unregistered retry is permitted after physics resumes.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 2
  initial_state: paused task_start with active arm/gripper controllers and exact formal Planning Scene
  policy: [/tmp/so101-acceptance-20260812-lzfOqk/install/so101_mujoco_demo_py/share/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, 6b741dc8a73f8e1845b3ba6f6c20196b691364294cd0023a0c33c7a33766375a]
  staged_approach_executable: [/tmp/so101-acceptance-20260812-lzfOqk/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/staged_approach, 70f76ef452976dcf6176f4559061822505e39baad1f465b6c02f5620222d6588]
  orchestration_script: [/tmp/so101_exp115_run.bash, 78b5ace85ef1e7c5f6b1caff8f40ea165fb6c42492ab7c9bb43b919bd2a16a16]
  pre_action_startup_attempt: The first shell exited while sourcing /opt/ros/jazzy/setup.bash because nounset was enabled too early; it never reached resume physics or any ROS state action. Nounset now starts only after all setup files load.
  phase_scripts:
    - [/tmp/so101_exp115_contact_hold.py, e81fc0309a0b5905efecf27ca62523468e2921fdf4011ff5f50a9e56bd42e0ba]
    - [/tmp/so101_exp115_micro_lift.py, 5351990b45096ed4c5540397b4a989f9b3cf2ea97592115815c4e4a45e5b82f4]
    - [/tmp/so101_exp115_policy_lift_waypoint1.py, 481ba41e04b48c1cfb52aa083fbcdf07bf644e9d66b1d7da0a41ac21af6746c9]
    - [/tmp/so101_exp115_remaining_lift.py, edbded505e9fa4bd8105e037ebf28a44b64fae07fe076595bea38f248168574b]
    - [/tmp/so101_exp115_transport.py, 2488c31d2e8bbf7db690bedde6e38bcff3e84e2d7583ffe0bf78e2e2e3a9eaa2]
    - [/tmp/so101_exp115_descend.py, dbaaa288b32cbf53c4a890019403de5e7c3273b8b78ea641ac2f66f9d70b275d]
    - [/tmp/so101_exp115_place_alignment.py, 28ee34861acfd88fb77619a282895378fec193edb872495b3c1c5cd6ce979b9b]
    - [/tmp/so101_exp115_release_retreat.py, 26f2fd77200fef2a25e183ebf122f487c209cfc7dc296cfbecb0b2b310813bea]
  phase_order:
    - resume physics
    - PRE_OPEN_GRIPPER plus MOVE_ABOVE_OBJECT plus DESCEND via staged_approach --stop-after DESCEND
    - bilateral low-force CONTACT_HOLD
    - physical CLOSE_GRIPPER plus MICRO_LIFT plus MoveIt collision-shadow attach
    - LIFT waypoint 1
    - remaining LIFT waypoints
    - TRANSPORT waypoints
    - DESCEND to off-table pre-release clearance
    - bounded closed-loop TCP alignment to pre-release cup target [-0.0788, -0.2475, 0.1835]
    - OPEN_GRIPPER plus immediate RETREAT plus Planning Scene detach/sync plus final evaluation
  place_alignment_tolerance_m: 0.003
  place_alignment_max_attempts: 3
  place_alignment_max_axis_correction_m: 0.030
  table_support_loss_grace_s: 0.05
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
preconditions:
  - EXP-114 proved epoch-2 task_start electronically and visually; the same owned simulator, MoveIt, RViz, and Viewer processes remain running.
  - All eight phase scripts are Ruff-clean, pycompile-clean, SHA-matched, and hard-code the same session and epoch.
  - Protected src/so101_gazebo_demo_py tracked status is empty.
success_criteria:
  - Every phase executes in the frozen order without reset, pause, process restart, direct state mutation, simulator attachment, or unbounded retry.
  - Physical bilateral contact and low-force grasp survive micro-lift, lift, transport, descent, and bounded place alignment.
  - Release settles the unconstrained cup upright, table-supported, within the unchanged red-ring target; final evaluator observes at least five fresh stable samples spanning 0.20 s.
  - Final Planning Scene has table=1, pedestal=1, plastic_cup=13 at the observed pose, expected colors, and no attached object; final gripper contact is zero.
  - Passive CUA shows RViz left and MuJoCo Viewer right with the cup inside the target ring and the arm retreated.
failure_criteria: Any phase, planning, execution, convergence, contact, force, support, alignment, placement, scene, provenance, or visual gate failure stops the cycle immediately and is retained as a valid failure.
invalid_criteria: Any reset/pause after resume, object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, model/config mutation, process restart, missing phase evidence, or action outside this preregistration invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Diagnose only the first failed phase, or record the first qualified full-cycle success and proceed to production runner/gates.
```

## Experiment EXP-115 Terminal Result

```yaml
experiment_id: EXP-115
status: VALID
terminal_result: BEHAVIORAL_FAILURE_STALE_LITERAL_RESET_EPOCH_IN_REMAINING_LIFT_GATE
terminal_time: 2026-08-12T04:57:29+08:00
command: bash /tmp/so101_exp115_run.bash
exit_code: 1
completed_phases:
  - staged approach: CLOSE_READY after 15 executed segments
  - contact hold: CONTACT_ONLY_PROVED with q6=-0.048507025 and 201 samples
  - micro lift: PHYSICAL_MICRO_LIFT_PROVED with 0.001967381 m lift and bilateral contact
  - first policy lift waypoint: POLICY_LIFT_WAYPOINT1_PHYSICAL_TRANSFER_PROVED with 0.008086705 m lift
failure:
  phase: remaining_lift
  error: RuntimeError MuJoCo pause/reset during bilateral gate
  exact_cause: The post-waypoint call retained stable_bilateral(0) from the original epoch-0 diagnostic instead of using before.reset_epoch. The same latent literal also existed in transport.
  actual_terminal_reset_epoch: 2
  actual_terminal_paused: false
  terminal_cup_position_m: [0.0199975741292537, -0.2685622106962029, 0.1897583781660382]
  terminal_bilateral_contact_counts: [3, 1]
  terminal_maximum_normal_force_n: 0.8083875446423894
  direct_object_state_writes: 0
  simulator_constraint_calls: 0
visual_acceptance:
  rviz_left_mujoco_right: true
  arm_in_non_task_start_lift_pose: true
  cup_physically_held_between_fingertips: true
  cup_lifted_clear_of_table: true
  table_pedestal_target_ring_robot_cup_visible: true
  viewer_running: true
evidence:
  staged_approach_json_sha256: f1a149118b322ae9ab746ff5107de4c4b854091865e2071e8240042a5fc2d10e
  contact_hold_json_sha256: 35104f4677b3c1c99e99bfa9dc224d986abd25c8e9137db5f6fbab1e446776ae
  micro_lift_json_sha256: 24e1a2f70755d357671c77bb9bdc342ce6400e2e95602ef46872a1bc9451d3e3
  first_lift_json_sha256: d67b7aee521965f80c14e61a0d3417377dfbf7e335dc90b4a8406ceef0c68ae8
  remaining_lift_json_sha256: 21ea623e5c0387e75c685172ab66ec034cb4c9e935864915674b4e37c765a261
  master_log_sha256: fe410afef1d9775f0bd38ec62521fbd2befa1d11aab9ee7ac373854275cc47a0
  terminal_evidence_sha256: effdee73791e13ee9527c9f98322c927d2b2c7024a490e2df25105b0772e7123
  terminal_cua_sha256: ca742d689dcb5f921be9762ad298649a5362bf6ea024d61d2b0174f6f00cd499
decision: Preserve this as a valid full-cycle failure. Replace only the two stale epoch-0 literals with the observed current epoch, qualify ResetWorld from the still-held state, and rerun the entire cycle from task_start; this partial run cannot count as success.
```

## Checkpoint CP-150

```yaml
checkpoint_id: CP-150
checkpoint_time: 2026-08-12T04:57:29+08:00
last_valid_experiment: EXP-115 VALID behavioral failure
current_hypothesis: Using the transaction's observed reset epoch for post-waypoint bilateral gates removes the false provenance failure without changing physical motion or contact acceptance.
working_tree_status: Intentional Task 13/14 source/model/plan/ledger/fork state remains. Protected src/so101_gazebo_demo_py tracked status is empty. Simulator remains epoch 2, running, with cup physically held and lifted.
confirmed_conclusions:
  - The fresh full cycle proved all phases through the first formal lift waypoint in one uninterrupted run.
  - Failure was caused by a deterministic stale diagnostic literal, not loss of grasp, force exceedance, pause, reset, or physical instability.
  - Both remaining_lift and transport copies now use stable_bilateral(before.reset_epoch); they are Ruff-clean and pycompile-clean.
next_command: Preregister and execute one qualified ResetWorld from epoch 2 to 3, restore the exact Planning Scene, then preregister a fresh full cycle with updated phase hashes.
```

## Experiment EXP-116

```yaml
experiment_id: EXP-116
prior_experiment: EXP-115 VALID behavioral failure while physically held
status: RUNNING
lifecycle: QUALIFIED_RESETWORLD_AFTER_FULL_CYCLE_FAILURE
run_mode: one_task_start_transaction_then_exact_scene_restore
hypothesis: The qualified ResetWorld implementation safely recovers the physically held epoch-2 failure state to a paused epoch-3 task_start with active controllers and exact formal Planning Scene.
single_variable: Execute exactly one ResetWorld(task_start) transaction and formal Planning Scene restore. No motion planning, gripper command, physics/model/config change, direct object-state write, or hidden constraint is permitted.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 2
  expected_new_reset_epoch: 3
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_script: [/tmp/so101_exp116_reset.py, 3e064d923e7a8dcc00ff9506ba59facef496a65d00f08848bb5519748cfde40c]
preconditions:
  - Same owned stack remains epoch 2 and running with active controllers, physical bilateral grasp, lifted cup, and MoveIt collision shadow attached.
  - EXP-115 terminal evidence and passive CUA were captured before this preregistration.
  - Reset script is Ruff-clean, pycompile-clean, and SHA-matched; it uses the qualified bounded-drain client.
success_criteria:
  - Reset receipt is exactly 2 -> 3 at authoritative step 0; final evidence is paused, cup is within 3 mm of task_start, all six joints are within 0.002 rad, and arm/gripper controllers are active.
  - Planning Scene readback is exactly table=1, pedestal=1, plastic_cup=13 with expected colors and no attached object.
  - Passive CUA shows horizontal task-start arm, open gripper clear of upright original cup, complete scene, and visible PAUSE.
failure_criteria: Any reset, epoch, joint, object, controller, scene, provenance, or visual mismatch blocks the rerun.
invalid_criteria: Any unrecorded state action, process restart, model/config mutation, direct object-state write, simulator attachment, or missing visual evidence invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh full cycle at epoch 3 only after VALID reset and visual acceptance.
```

## Experiment EXP-116 Terminal Result

```yaml
experiment_id: EXP-116
status: VALID
terminal_result: BEHAVIORAL_FAILURE_STALE_MOVEIT_ATTACHMENT_SURVIVED_PHYSICAL_RESET
terminal_time: 2026-08-12T04:59:00+08:00
command: python3 /tmp/so101_exp116_reset.py
exit_code: 1
result:
  reset_receipt: {old_epoch: 2, new_epoch: 3, simulation_step: 0, keyframe: task_start}
  final_paused: true
  final_cup_position_m: [0.02, -0.28, 0.165]
  final_joint_positions_rad: [0.000000007587183007158268, 0.00003223533334847307, 0.00002938616047419338, 0.0000024632646104060205, 0.0000000008462017928351062, -0.000000022938828005989564]
  controllers_active: true
  planning_scene_world_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_attached_object_ids: [plastic_cup]
diagnosis:
  - The physical MuJoCo reset fully succeeded, but make_task_scene only added the world cup and never emitted a REMOVE operation for a stale attached collision shadow from the previous cycle.
  - ResetWorld therefore was not yet a complete cross-system transaction for repeated experiments; leaving the attached cup would corrupt the next MoveIt planning state.
evidence:
  reset_json_sha256: 1be18f5c308ea35a21c6ecee871486ce0565344c56e5343220fe5e9ac319c097
  reset_log_sha256: 8d0ebb4fa2b3b27890ee474524dc7b9c5a0858ae12e43165c4a6d493073aec97
decision: Preserve as a valid failure. Make formal task-scene restoration explicitly remove attached plastic_cup before adding the world geometry, prove it with a RED/GREEN contract test, rebuild the overlay, and repeat one full reset transaction.
```

## Checkpoint CP-151

```yaml
checkpoint_id: CP-151
checkpoint_time: 2026-08-12T05:00:51+08:00
last_valid_experiment: EXP-116 VALID behavioral failure
current_hypothesis: A PlanningScene diff containing AttachedCollisionObject plastic_cup with CollisionObject.REMOVE atomically clears the old collision shadow while restoring the 13-primitive world cup.
working_tree_status: Intentional Task 13/14 state plus scene_setup.py and its contract test. Protected src/so101_gazebo_demo_py tracked status is empty. Physical simulator is paused at epoch-3 task_start; stale MoveIt attachment remains pending formal reset.
confirmed_conclusions:
  - New regression test failed before the fix because make_task_scene returned zero attached operations.
  - make_task_scene now emits exactly one attached plastic_cup REMOVE operation and the complete world geometry; all four focused scene tests pass with source PYTHONPATH.
  - Ruff passes and so101_mujoco_demo_py has been rebuilt into the active fresh overlay.
  - scene_setup source SHA is 4125cbb3ba87222bca9323572d6e3d1d381d503acc50261e7b20a136947fc66f and test SHA is 7b536457118c7e8d94ab7e775d3bd9b85a065cae1216f1cb1f7cce1d17ce99bd.
next_command: Preregister and execute one epoch 3 -> 4 ResetWorld transaction using the rebuilt formal scene restore, then obtain passive CUA proof.
```

## Experiment EXP-117

```yaml
experiment_id: EXP-117
prior_experiment: EXP-116 VALID cross-system reset failure
status: RUNNING
lifecycle: ATTACHMENT_CLEAN_RESETWORLD_REQUALIFICATION
run_mode: one_task_start_transaction_then_attachment_clean_scene_restore
hypothesis: The rebuilt formal task scene removes the stale MoveIt attachment and restores exact world geometry, completing a valid epoch 3 -> 4 ResetWorld transaction.
single_variable: Add only the explicit attached plastic_cup REMOVE operation to make_task_scene. Physical model, controller setup, reset client, keyframe, geometry, colors, thresholds, and session remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 3
  expected_new_reset_epoch: 4
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  scene_setup_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/scene_setup.py, 4125cbb3ba87222bca9323572d6e3d1d381d503acc50261e7b20a136947fc66f]
  scene_setup_test: [src/so101_mujoco_demo_py/test/test_scene_setup_contract.py, 7b536457118c7e8d94ab7e775d3bd9b85a065cae1216f1cb1f7cce1d17ce99bd]
  reset_script: [/tmp/so101_exp117_reset.py, e66e3d13d7faed889f5bebe4f3960f1a980b046f5b87cb376c4ccae53d954db6]
preconditions:
  - Same owned simulator is paused at authoritative epoch 3 step 0 with physical task_start state and active controllers.
  - The stale Planning Scene attachment from EXP-116 is intentionally present, making this a non-vacuous cleanup test.
  - Focused tests, Ruff, build, pycompile, and SHA checks pass before state action.
success_criteria:
  - Reset receipt is exactly 3 -> 4 at authoritative step 0; final state is paused, cup within 3 mm, all six joints within 0.002 rad, and controllers active.
  - Planning Scene readback is table=1, pedestal=1, plastic_cup=13 with expected colors and no attached objects.
  - Passive CUA shows RViz left, Viewer right, horizontal task-start arm, open gripper clear of original upright cup, complete scene, and visible PAUSE.
failure_criteria: Any reset, epoch, joint, object, controller, scene cleanup, provenance, or visual mismatch blocks the rerun.
invalid_criteria: Any unrecorded state action, process restart, model/config mutation, direct state write, simulator constraint, or missing CUA evidence invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: One fresh full-cycle attempt at epoch 4 only after VALID reset and visual acceptance.
```

## Experiment EXP-117 Terminal Result

```yaml
experiment_id: EXP-117
status: VALID
terminal_result: PRE_ACTION_FAILURE_FRESH_SUBSCRIBER_CANNOT_READ_ALREADY_PAUSED_SENSOR_QOS
terminal_time: 2026-08-12T05:01:10+08:00
command: python3 /tmp/so101_exp117_reset.py
exit_code: 1
result:
  reset_world_called: false
  physics_pause_calls: 0
  controller_switch_calls: 0
  physical_state_unchanged: true
  error: RuntimeError initial evidence unavailable
diagnosis:
  - The simulator was already paused before the fresh reset observer subscribed, and sensor-data QoS does not replay the last evidence frame.
  - MujocoResetClient previously called observer.snapshot directly before entering its transaction, so a fresh client could not take ownership of an already paused world.
decision: Preserve as a valid pre-action failure. Add bounded idempotent pause(true) snapshot acquisition to the production reset client, with a RED/GREEN test; let the reset client itself acquire initial provenance instead of requiring wrapper pre-read.
```

## Checkpoint CP-152

```yaml
checkpoint_id: CP-152
checkpoint_time: 2026-08-12T05:04:40+08:00
last_valid_experiment: EXP-117 VALID pre-action failure
current_hypothesis: A fresh paused-world client can request an authoritative current snapshot through bounded idempotent pause(true), then execute the unchanged reset transaction without QoS durability changes.
working_tree_status: Intentional Task 13/14 changes plus production reset initial-snapshot acquisition and regression test. Protected src/so101_gazebo_demo_py tracked status is empty. Simulator remains paused at epoch-3 task_start with stale MoveIt attachment.
confirmed_conclusions:
  - New test failed before the fix with EvidenceStale from the first observer snapshot.
  - Production client now first consumes any fresh frame without service action; only on typed EvidenceStale does it request pause(true) at no more than 20 Hz while draining subscriptions.
  - All 22 reset tests pass, Ruff passes, and so101_mujoco_demo_py is rebuilt into the active overlay.
  - Reset source SHA is bf78b0eed961092835ee9c82e8f8c22c6a4dfe1fff7f4d4a39f9c3949b35009d and test SHA is 63480ee6394c0516158ec2d35e353f2089d8709da4a67bc4bb9a5d81e0b79d1c.
next_command: Preregister EXP-118, exercise the production client's paused-world acquisition, reset epoch 3 -> 4, clean stale attachment, and obtain passive CUA evidence.
```

## Experiment EXP-118

```yaml
experiment_id: EXP-118
prior_experiment: EXP-117 VALID paused-subscriber pre-action failure
status: RUNNING
lifecycle: PAUSED_CLIENT_AND_ATTACHMENT_CLEAN_RESETWORLD_REQUALIFICATION
run_mode: fresh_client_snapshot_then_one_task_start_transaction_and_exact_scene_restore
hypothesis: The rebuilt client acquires current epoch-3 paused evidence through one bounded idempotent snapshot request, ResetWorld advances to epoch 4, and formal scene restoration removes the stale attached cup.
single_variable: Add only production initial-snapshot acquisition on EvidenceStale; all EXP-117 scene cleanup, reset, geometry, controller, keyframe, thresholds, and session inputs remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 3
  expected_new_reset_epoch: 4
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py, bf78b0eed961092835ee9c82e8f8c22c6a4dfe1fff7f4d4a39f9c3949b35009d]
  reset_test: [src/so101_mujoco_demo_py/test/test_mujoco_reset.py, 63480ee6394c0516158ec2d35e353f2089d8709da4a67bc4bb9a5d81e0b79d1c]
  scene_setup_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/scene_setup.py, 4125cbb3ba87222bca9323572d6e3d1d381d503acc50261e7b20a136947fc66f]
  reset_script: [/tmp/so101_exp118_reset.py, 398cb26d75839b73b90476fef829052a3c53431a3fd20eb99274d890b6170ebc]
preconditions:
  - Same simulator is paused at epoch 3 step 0 and has emitted no replayable sample to the new client; stale Planning Scene attachment remains.
  - Focused tests, Ruff, build, pycompile, and SHA checks pass; wrapper intentionally performs no observer pre-read.
success_criteria:
  - Production client obtains initial epoch-3 provenance without timeout or retry storm; receipt is exactly 3 -> 4 at step 0.
  - Final state is paused, cup within 3 mm, all joints within 0.002 rad, controllers active, exact world geometry/colors present, and attached object list empty.
  - Passive CUA shows RViz left, Viewer right, horizontal task-start arm, open gripper clear of original upright cup, complete scene, and visible PAUSE.
failure_criteria: Any snapshot, reset, epoch, joint, object, controller, scene cleanup, provenance, or visual mismatch blocks the full-cycle rerun.
invalid_criteria: Any unrecorded action, process restart, model/config change, direct state write, simulator constraint, or missing visual evidence invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh full-cycle attempt at epoch 4 only after VALID reset and visual acceptance.
```

## Experiment EXP-127 Terminal Result

```yaml
experiment_id: EXP-127
status: VALID
terminal_result: BEHAVIORAL_FAILURE_FINAL_OUT_OF_REGION_AFTER_PHYSICAL_RELEASE_AND_RETREAT
terminal_time: 2026-08-12T05:28:34+08:00
command: python3 /tmp/so101_exp127_release_retreat.py
exit_code: 1
result:
  release_completed: true
  retreat_waypoints_completed: 3
  planning_scene_attachment_ids: []
  planning_scene_world_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  final_table_contact: true
  final_gripper_contact_counts: {left: 0, right: 0}
  final_upright_tilt_rad: 0.016152592261982922
  final_cup_position_m: [-0.0790507188907473, -0.26109349992666697, 0.1654421668216515]
  target_x_bounds_m: [-0.085, -0.075]
  target_y_bounds_m: [-0.255, -0.245]
  target_y_miss_m: -0.006093499926666965
  error: RuntimeError final placement failed FINAL_OUT_OF_REGION
diagnosis:
  - The physical q6 release, three collision-checked retreat waypoints, detach/world-scene sync, table support, upright, zero-gripper-contact, and stability gates all passed.
  - From the verified pre-release alignment sample to the settled final sample, the unconstrained cup shifted [-0.0008601825, -0.0149821894, -0.0172304940] m during release and retreat.
  - The unchanged target region rejected the final y position by 6.09 mm. This diagnostic cannot count as a successful pick-and-place.
evidence:
  release_retreat_json_sha256: f583c5ad26e90925208685266611a48a6ff7b713e2cd79bee71661e5b349dbff
  release_retreat_log_sha256: 782f465dd5b8b83ddd3f2cc7214a3ad0743751ae55436a145f2a76351c3a20ba
decision: Keep the target region and all success thresholds unchanged. Compensate the measured y settling shift in the MuJoCo-only pre-release target, reset, and rerun one uninterrupted full lifecycle.
```

## Checkpoint CP-158

```yaml
checkpoint_id: CP-158
checkpoint_time: 2026-08-12T05:32:29+08:00
last_valid_experiment: EXP-127 VALID final-out-of-region failure
current_hypothesis: A pre-release y compensation of +0.0150 m cancels the measured -0.014982 m unconstrained settling shift while preserving the unchanged final target bounds.
working_tree_status: Intentional Task 13/14 changes plus the MuJoCo-only place-settling compensation. Protected Gazebo package remains unmodified. Simulator remains running at epoch 6 after physical release and retreat; cup is stable on the table outside the target.
change:
  policy_file: src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml
  old_place_settling_compensation_m: [0.0012, 0.0025, 0.0185]
  new_place_settling_compensation_m: [0.0012, 0.0150, 0.0185]
  final_target_bounds_changed: false
  policy_sha256: bc06bd8afd4936ca05653c19f720c5f2e2db339eb34bc4a426b4a1a2ba513205
  test_sha256: bcfb3f60a66a12a79593ce76fc07139ad95afa64da50d8e893bbb44dbc0b6682
verification:
  place_alignment_tests: 7 passed
  ruff: passed
  overlay_build: passed
next_command: Preregister one qualified ResetWorld epoch 6 to 7, visually verify task_start, then preregister and execute a fresh full cycle using the frozen compensated target.
```

## Experiment EXP-119 Terminal Result

```yaml
experiment_id: EXP-119
status: VALID
terminal_result: QUALIFIED_FRESH_PAUSED_CLIENT_RESET_AND_SCENE_CLEANUP
terminal_time: 2026-08-12T05:07:00+08:00
command: python3 /tmp/so101_exp119_reset.py
exit_code: 0
result:
  reset_receipt: {old_epoch: 3, new_epoch: 4, simulation_step: 0, keyframe: task_start}
  final_paused: true
  controllers_active: true
  final_cup_position_m: [0.02, -0.28, 0.165]
  planning_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_color_ids: [pedestal, plastic_cup, table]
  planning_scene_attached_object_ids: []
visual_acceptance:
  rviz_left_mujoco_right: true
  horizontal_task_start_arm: true
  open_gripper_clear_of_cup: true
  upright_cup_at_original_position: true
  table_pedestal_target_ring_robot_cup_visible: true
  viewer_pause_visible: true
evidence:
  reset_json_sha256: e4f397767a87c2c2c499590166e44320cd96a645043d7fcca1233c9179e56ea5
  reset_log_sha256: 7c58f5e1f3c402d9f0f630fdbd933d21a9260af6a5d804b2d7ea7b5f6f30cfbf
  post_reset_cua_sha256: 8420a6a1cc8a0b1158bc874474832ce6a59f14f102b6d5a5d9f2dd48c8b434ae
decision: ResetWorld is now qualified as a repeatable cross-system experiment boundary for a fresh client joining an already paused world, including stale MoveIt attachment cleanup and CUA visual proof.
```

## Checkpoint CP-154

```yaml
checkpoint_id: CP-154
checkpoint_time: 2026-08-12T05:08:00+08:00
last_valid_experiment: EXP-119 VALID qualified reset
current_hypothesis: With stale epoch literals fixed and the measured pre-release alignment enabled, a fresh epoch-4 full cycle completes the physical placement inside the red ring.
working_tree_status: Intentional Task 13/14 changes including reset and scene fixes. Protected src/so101_gazebo_demo_py tracked status is empty. Simulator is paused at exact epoch-4 task_start with active controllers and clean formal Planning Scene.
confirmed_conclusions:
  - Repeated ResetWorld now works from a genuinely fresh paused client and cleans both physical and MoveIt state.
  - EXP-115's only full-cycle failure was a stale epoch-0 literal after a successfully executed first remaining-lift waypoint; both remaining_lift and transport now derive the current epoch.
  - All EXP-120 phase scripts are Ruff-clean, pycompile-clean, session-bound to so101-task14-acceptance, and epoch-bound to 4.
next_command: Preregister and execute one uninterrupted epoch-4 full physical pick-place.
```

## Experiment EXP-120

```yaml
experiment_id: EXP-120
prior_experiment: EXP-119 VALID qualified reset
status: RUNNING
lifecycle: FULL_PHYSICAL_PICK_PLACE_WITH_CLOSED_LOOP_ALIGNMENT
run_mode: one_uninterrupted_epoch_4_staged_cycle
hypothesis: The qualified physical phase contracts plus corrected current-epoch gates and bounded alignment complete one physical pick-place with the stable cup inside the unchanged target.
single_variable: Replace only the two stale post-waypoint epoch literals with the observed current epoch. All motion targets, physical/contact gates, place compensation, geometry, model, controller, scene, and phase order remain unchanged from EXP-115.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 4
  initial_state: paused task_start with active controllers and exact attachment-free formal Planning Scene
  policy: [/tmp/so101-acceptance-20260812-lzfOqk/install/so101_mujoco_demo_py/share/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, 6b741dc8a73f8e1845b3ba6f6c20196b691364294cd0023a0c33c7a33766375a]
  staged_approach_executable: [/tmp/so101-acceptance-20260812-lzfOqk/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/staged_approach, 70f76ef452976dcf6176f4559061822505e39baad1f465b6c02f5620222d6588]
  orchestration_script: [/tmp/so101_exp120_run.bash, 885d9e9095e750996a7835e8e042cad3ff54419df60a1b5aeae2cbd9f526929b]
  phase_scripts:
    - [/tmp/so101_exp120_contact_hold.py, 55c11d03bf7b5529a5b42778e24bb8d967f48f717e8d927c7bd3e0972f059f75]
    - [/tmp/so101_exp120_micro_lift.py, 922b92e979134a377193295ae0df91ab55bd40ae375b8551d38078d53c4fc838]
    - [/tmp/so101_exp120_policy_lift_waypoint1.py, 4c00923b6fe3017e1416ebda750a30892c6b690ade5d8f34dbcc36ae3ebb7b25]
    - [/tmp/so101_exp120_remaining_lift.py, 19656fe8f2751fa88e86898efb510b22cfa50f9b99a62e05876c98bb4cbd6d60]
    - [/tmp/so101_exp120_transport.py, 87d1d75cf9c05091335f7d0437f1d2142a7211945d7a764fe0d3657d14952ef0]
    - [/tmp/so101_exp120_descend.py, d16d513d93c29993483f43c521ce81e970c61f4b7270acf6db0b6712add9105e]
    - [/tmp/so101_exp120_place_alignment.py, ac4c8ad5ab5fe4eb4ca7db406c58d1d9dbccd415a4a00ac1909ec8500805b705]
    - [/tmp/so101_exp120_release_retreat.py, c6846d61e6ebdcabbc3c4474322fcb286642a1aca5241d64058408e85e26c245]
  phase_order: [resume, staged_approach, contact_hold, micro_lift_attach_shadow, lift_waypoint_1, remaining_lift, transport, descend_to_pre_release_clearance, bounded_place_alignment, release_retreat_detach_sync_final_evaluation]
  place_alignment_target_m: [-0.0788, -0.2475, 0.1835]
  place_alignment_tolerance_m: 0.003
  place_alignment_max_attempts: 3
  place_alignment_max_axis_correction_m: 0.030
  table_support_loss_grace_s: 0.05
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
preconditions:
  - EXP-119 electronically and visually proves exact epoch-4 task_start and attachment-free scene on the same owned stack.
  - All scripts pass Ruff, pycompile, provenance scan, and SHA matching before resume.
success_criteria:
  - Every phase completes in order without reset/pause/process restart/direct state write/simulator attachment/unbounded retry.
  - Bilateral physical grasp survives lift, transport, descent, and bounded alignment under force/contact gates.
  - Release settles the unconstrained upright cup table-supported inside the unchanged target for at least five fresh stable samples over 0.20 s.
  - Final scene has table=1, pedestal=1, 13-primitive plastic_cup at observed pose, colors, no attachment, and zero gripper contact.
  - Passive CUA shows RViz left, Viewer right, cup inside red ring, and arm retreated.
failure_criteria: Any phase, planning, execution, convergence, contact, force, support, alignment, placement, scene, provenance, or visual gate failure stops immediately and is retained.
invalid_criteria: Any reset/pause after resume, direct object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, model/config mutation, process restart, missing evidence, or unregistered retry invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Diagnose only first failure, or record first full-cycle success and proceed to production runner/gates.
```

## Experiment EXP-125 Terminal Result

```yaml
experiment_id: EXP-125
status: VALID
terminal_result: PRE_DESCEND_FAILURE_STALE_STABLE_GATE_EPOCH_LITERAL
terminal_time: 2026-08-12T05:26:06+08:00
command: bash /tmp/so101_exp125_run.bash
exit_code: 1
result:
  transport_status: FORMAL_MOVE_ABOVE_PLACE_PROVED
  transport_waypoints_completed: 5
  transport_scaling: 0.05
  transport_force_boundary_passed: true
  descend_motion_started: false
  error: RuntimeError MuJoCo pause/reset during stable gate
diagnosis:
  - descend initial provenance correctly observed epoch 6, but called stable_gate(2) from the original diagnostic copy before issuing any descend trajectory.
  - The same literal occurred after each descend waypoint; both are replaced with before.reset_epoch. No physical policy or threshold changes.
evidence:
  master_log_sha256: 267dcaef04321ab44f73b7460d485a3f646e1f8a548e4d2c35642035f5db1a60
  transport_json_sha256: 269ce40d8c5dfcb36bd6e9f2637825ed837f08ab1aa9af92d444949bebd74d72
  descend_json_sha256: 1080c81ac5aa83b282e10c47df9a6d4cdd4cfa0365ef9ce3f23c3a77858818f8
decision: Do not count as full success. Preserve the proven transport endpoint, continue descend/alignment/release only as a registered diagnostic, then reset and rerun from task_start.
```

## Experiment EXP-126

```yaml
experiment_id: EXP-126
prior_experiment: EXP-125 VALID pre-descend literal failure
status: RUNNING
lifecycle: PRESERVED_STATE_DESCEND_ALIGNMENT_RELEASE_DIAGNOSTIC
run_mode: continue_from_verified_transport_endpoint
hypothesis: Using the observed epoch in descend stable gates allows the already qualified descend, bounded alignment, physical release, retreat, detach/sync, and final evaluator to complete.
single_variable: Replace only two stable_gate(2) calls with stable_gate(before.reset_epoch). No reset, pause, trajectory, threshold, scene, or model change.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 6
  initial_state: running, physically held cup at completed EXP-125 transport endpoint, attached collision shadow present
  continuation_script: [/tmp/so101_exp126_continue.bash, b0275c54f9db67cf23d1f4c48914ba6c9e1590675bf47615dd6b8f6267bbd933]
  descend_script: [/tmp/so101_exp126_descend.py, 43627c6f5a191d719e208ade17172221edb0a535bf03944ec91386860fddb7f8]
  place_alignment_script: [/tmp/so101_exp126_place_alignment.py, 764ed4fa41660cc374db6bcd764f0e7ab9f34500ec6f0aafccefe244d177c209]
  release_retreat_script: [/tmp/so101_exp126_release_retreat.py, 1aba97496af58361c164b7af2569a9e049fdf580cb8515d76e238fde63d62b59]
preconditions:
  - Same epoch-6 state is preserved; transport completed all five waypoints under force/contact gates; no descend action occurred.
  - Scripts pass Ruff, pycompile, and hashes; no state action after preregistration.
success_criteria:
  - Descend reaches pre-release clearance with physical grasp; alignment reaches target within 3 mm; release/retreat settles inside target and produces attachment-free scene.
failure_criteria: Any descend, alignment, release, support, placement, scene, force, contact, or provenance failure stops immediately.
invalid_criteria: Any reset/pause, direct state write, simulator attachment, model/config mutation, or unregistered retry invalidates diagnostic.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Qualified reset and fresh full cycle regardless of diagnostic result.
```

## Experiment EXP-126 Terminal Result

```yaml
experiment_id: EXP-126
status: VALID
terminal_result: PRE_RELEASE_FAILURE_STALE_PRE_ALIGNMENT_JOINT_HANDOFF
terminal_time: 2026-08-12T05:27:44+08:00
command: bash /tmp/so101_exp126_continue.bash
exit_code: 1
result:
  descend_status: FORMAL_DESCEND_TO_PRE_RELEASE_CLEARANCE_PROVED
  descend_waypoints_completed: 3
  alignment_status: PRE_RELEASE_ALIGNMENT_PROVED
  alignment_attempts: 1
  aligned_cup_position_m: [-0.078190536404924, -0.24611131054611562, 0.1826726608372338]
  release_action_started: false
  error: RuntimeError robot is not at EXP-108 physical endpoint
diagnosis:
  - Closed-loop alignment intentionally changed arm joints after the old EXP-108 descend endpoint.
  - Release already verifies live epoch, bilateral grasp, force, no table support, and cup position within 3 mm of the release target; requiring the pre-alignment joint vector is contradictory and redundant.
evidence:
  master_log_sha256: db0798610ae37c71104a64130a651443dc825d15b23761661590e5a59e6ea79a
  descend_json_sha256: a10acfb2e2796f0da18ccf2194f2ebaf37f38dbff8e9abfd3d65abdbdb7a583d
  alignment_json_sha256: f3755feb208478c21afe369096cce7f93288c1accf71ca9f9761f61787fd363f
  release_json_sha256: d746a271022d4fb307b57dd851fc7d13c155b75376781d6b9baf9e7925ce8820
decision: Preserve aligned held state. Remove only the obsolete pre-alignment arm-vector assertion; retain live alignment/contact/force/epoch/scene gates and continue release as a diagnostic.
```

## Experiment EXP-127

```yaml
experiment_id: EXP-127
prior_experiment: EXP-126 VALID pre-release handoff failure
status: RUNNING
lifecycle: PRESERVED_ALIGNED_STATE_RELEASE_RETREAT_FINAL_DIAGNOSTIC
run_mode: release_from_verified_alignment_then_retreat_detach_sync_evaluate
hypothesis: The live physical and alignment gates are the correct handoff contract, so release, retreat, scene sync, and final evaluation complete from the preserved aligned state.
single_variable: Remove only the obsolete EXPECTED_START_ARM assertion. All live gates, q6 target, retreat targets, support/force limits, final region, and session/epoch remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 6
  aligned_cup_position_m: [-0.078190536404924, -0.24611131054611562, 0.1826726608372338]
  release_target_m: [-0.0788, -0.2475, 0.1835]
  release_script: [/tmp/so101_exp127_release_retreat.py, 61e5e588b8ce68d90cd9a8e44a5fef6aac1442d5743d6434b993ced7b9685346]
preconditions:
  - Same epoch-6 state remains running, aligned within 3 mm, physically bilateral, off-table, force-safe, and MoveIt shadow attached.
  - No release action occurred; script passes Ruff, pycompile, and hash checks.
success_criteria:
  - q6 opens, cup gains stable table support, retreat removes all gripper contact, scene detaches/syncs 13 world primitives, and final evaluator passes unchanged target/stability gates.
failure_criteria: Any release, support, retreat, contact, force, scene, target, stability, or provenance gate failure stops immediately.
invalid_criteria: Any reset/pause, direct object write, simulator attachment, model/config change, or unregistered retry invalidates diagnostic.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Qualified reset and fresh full cycle regardless of result.
```

## Experiment EXP-123 Terminal Result

```yaml
experiment_id: EXP-123
status: VALID
terminal_result: BEHAVIORAL_FAILURE_TRANSPORT_FORCE_BOUNDARY_EXCEEDED
terminal_time: 2026-08-12T05:21:00+08:00
command: bash /tmp/so101_exp123_run.bash
exit_code: 1
completed_phases: [staged_approach, contact_hold, micro_lift, first_lift_waypoint, remaining_lift, transport_waypoints_1_to_4]
failure:
  phase: transport waypoint 5 monitor
  error: MOVEIT_EXECUTION_MONITOR_ABORTED force boundary exceeded during transport
  maximum_allowed_force_n: 11.60
  terminal_reset_epoch: 5
  terminal_paused: false
  terminal_cup_position_m: [-0.07804321329331593, -0.26427221632293524, 0.2284816389310016]
  terminal_bilateral_contact: true
  terminal_settled_force_n: 2.7848259288872956
  terminal_table_contact: false
diagnosis:
  - The new 50 ms contact-loss guard removed the prior single-frame contact abort and exposed a distinct transient force spike at the same final transport segment.
  - The 11.60 N force boundary remains a hard gate and is not relaxed. The safe independent variable is transport velocity/acceleration, currently 0.10.
evidence:
  master_log_sha256: 7f7d7202e2d6b4f5eff23150989ea538660ddc42e716303091e4dba1b85544f7
  transport_json_sha256: 47a12dee1bef1760f05fc022447f44d0e142dcec8f2b387c35123ae79d7ef5bd
  terminal_joints_sha256: 05f313c3308da53841476f77fbd039bdaec2cf34a36eb51294f4b9d04ab992c6
  terminal_evidence_sha256: 65abeb2d131da999a8db590f93d31d54cd841a8e105d87075a1351dbd44da324
decision: Do not count. Preserve the force threshold, reduce only transport velocity and acceleration scaling from 0.10 to 0.05, reset, and rerun the full cycle.
```

## Experiment EXP-124

```yaml
experiment_id: EXP-124
prior_experiment: EXP-123 VALID transport force failure
status: RUNNING
lifecycle: QUALIFIED_RESETWORLD_AFTER_TRANSPORT_FORCE_FAILURE
run_mode: one_task_start_transaction_then_attachment_clean_scene_restore
hypothesis: Qualified ResetWorld recovers the held epoch-5 transport endpoint to clean paused epoch-6 task_start.
single_variable: Execute only unchanged ResetWorld(task_start) and exact scene restore.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 5
  expected_new_reset_epoch: 6
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  reset_script: [/tmp/so101_exp124_reset.py, c258971f1015bd02fee2786538f1a408702f88b1a25885a615ff4a772a9cdc44]
preconditions:
  - Same epoch-5 owned stack is running, controllers active, cup physically held, and MoveIt collision shadow attached.
  - Reset script and current client pass Ruff, pycompile, tests, build, and hashes.
success_criteria:
  - Receipt exactly 5 -> 6 at step 0; paused task_start object/joints, active controllers, exact attachment-free scene satisfy unchanged gates.
failure_criteria: Any reset, convergence, scene cleanup, or provenance mismatch blocks rerun.
invalid_criteria: Any unregistered motion, process restart, model/config mutation, direct state write, or simulator constraint invalidates run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh epoch-6 full cycle with transport scaling 0.05 only after VALID reset.
```

## Experiment EXP-124 Terminal Result

```yaml
experiment_id: EXP-124
status: VALID
terminal_result: QUALIFIED_RESETWORLD_AFTER_FORCE_FAILURE
terminal_time: 2026-08-12T05:22:30+08:00
command: python3 /tmp/so101_exp124_reset.py
exit_code: 0
result:
  reset_receipt: {old_epoch: 5, new_epoch: 6, simulation_step: 0, keyframe: task_start}
  final_paused: true
  controllers_active: true
  planning_scene_attached_object_ids: []
evidence:
  reset_json_sha256: 9c800a8fca69532ec36cdd4a788a3f4d81a355494507013cd4d78be22400d7dc
  reset_log_sha256: 26063affa6d6d4ebbca9c28656e65734868b5c363aab80c9d81b70e5221b1cd3
decision: Start a fresh epoch-6 full cycle with only transport scaling reduced.
```

## Experiment EXP-125

```yaml
experiment_id: EXP-125
prior_experiment: EXP-124 VALID qualified reset
status: RUNNING
lifecycle: FULL_PHYSICAL_PICK_PLACE_LOW_IMPACT_TRANSPORT
run_mode: one_uninterrupted_epoch_6_staged_cycle
hypothesis: Reducing transport velocity and acceleration scaling from 0.10 to 0.05 removes the transient force spike while preserving the physical grasp and all unchanged acceptance gates.
single_variable: transport velocity_scaling and acceleration_scaling are 0.05 instead of 0.10. Force threshold remains 11.60 N; contact grace remains 0.05 s; all other inputs are frozen.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 6
  initial_state: paused exact task_start with active controllers and clean scene
  orchestration_script: [/tmp/so101_exp125_run.bash, d3900ca765fc49168a1db71b5f3a8d4fb85fe0d27870473b8540ba1ca337c7c6]
  phase_scripts:
    - [/tmp/so101_exp125_contact_hold.py, 9d747455c2691bfddad632d3521fd2a571fe946d7746ae48347436790b71d388]
    - [/tmp/so101_exp125_micro_lift.py, 3638834212170859fb9f6a2c4774a14b1063f871c22dcf6a715ac9d447bd76d4]
    - [/tmp/so101_exp125_policy_lift_waypoint1.py, b6a268ae62613733a5b9d3983f30bfb3510e413a21200e90534a9837bcf89d5c]
    - [/tmp/so101_exp125_remaining_lift.py, 18f65f7b04b4e369b13238677ac98f1cc4758ba4ceec0baebd414da357dd9592]
    - [/tmp/so101_exp125_transport.py, 2774278ad750447dacb161a0265cb4c7d080104228b5a132bbda9e80f15380c4]
    - [/tmp/so101_exp125_descend.py, 82079f8ef2303331203d09272cde8b6633f22e54c6e710f8f3dbff995038972b]
    - [/tmp/so101_exp125_place_alignment.py, 8a3d8f03bb0d758a2ea7533bfc734bde115bba9dd36e773737bc647cfd8bf40a]
    - [/tmp/so101_exp125_release_retreat.py, 18434b1801adaf6b4f39fd02cbc318c51edc03c97626291a1a2c472538c2c6d1]
  transport_scaling: {velocity: 0.05, acceleration: 0.05}
  maximum_force_n: 11.60
  contact_loss_grace_s: 0.05
  place_alignment_target_m: [-0.0788, -0.2475, 0.1835]
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
preconditions:
  - Same owned epoch-6 stack is paused at task_start; scripts pass Ruff, pycompile, SHA, and protected Gazebo checks.
success_criteria:
  - All phases complete in order, force never exceeds 11.60 N, sustained contact remains bilateral, and no prohibited state action occurs.
  - Release settles unconstrained cup upright/table-supported inside target; final scene detached/synced; passive CUA shows successful placement and retreat.
failure_criteria: Any phase, force, sustained contact, support, alignment, placement, scene, provenance, or visual gate failure stops immediately.
invalid_criteria: Any reset/pause after resume, direct state write, teleport, simulator constraint, model/config mutation, process restart, missing evidence, or unregistered retry invalidates run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Diagnose only first failure, or record first full-cycle success and proceed to production runner/gates.
```

## Experiment EXP-120 Terminal Result

```yaml
experiment_id: EXP-120
status: VALID
terminal_result: BEHAVIORAL_FAILURE_SINGLE_SAMPLE_TRANSPORT_CONTACT_MONITOR_ABORT
terminal_time: 2026-08-12T05:12:11+08:00
command: bash /tmp/so101_exp120_run.bash
exit_code: 1
completed_phases:
  - staged approach: CLOSE_READY after 15 segments
  - contact hold: CONTACT_ONLY_PROVED
  - micro lift: PHYSICAL_MICRO_LIFT_PROVED
  - first policy lift waypoint: POLICY_LIFT_WAYPOINT1_PHYSICAL_TRANSFER_PROVED
  - remaining lift: REMAINING_FORMAL_LIFT_PROVED after 4 segments
  - transport waypoints 1 through 4: completed and recorded
failure:
  phase: transport waypoint 5 monitor
  wrapper_error: MOVEIT_EXECUTION_MONITOR_ABORTED
  controller_terminal_status: SUCCEEDED
  move_group_terminal_status: SUCCEEDED
  endpoint_maximum_joint_residual_rad: 0.000530535
  terminal_joint_positions_rad: [0.39434280843720515, 0.2112483299802611, 0.10994771952116496, 1.1747040661819488, 0.001602909366881152, -0.04813173336122323]
  terminal_cup_position_m: [-0.07801247910015179, -0.2642998316584434, 0.22834796143610123]
  terminal_reset_epoch: 4
  terminal_paused: false
  terminal_bilateral_contact: true
  terminal_maximum_normal_force_n: 2.807418031601841
  terminal_table_contact: false
diagnosis:
  - The final transport trajectory physically reached its target and both lower layers returned success.
  - Before the successful MoveIt result future reached the client, the transport monitor observed one instantaneous bilateral-contact false sample and cancelled because it had no grace window.
  - All adjacent stages already use a 50 ms SustainedConditionGuard for contact/support manifold handoffs; transport was the remaining immediate single-sample gate.
evidence:
  master_log_sha256: 2254463fec34277f2824d9f10defd8ffacc9dd41f2627ea6e80b25946d9b7edf
  transport_json_sha256: 50f10d69ec372f69d69e2e6f3b3728bb37b5015acf151967b2b0045c853debaa
  terminal_joints_sha256: d643919cc9e9310a6f7642432a838f0bf43ce077b7d68416e2fa5dbca79af7bb
  terminal_evidence_sha256: 3c1461ea20fdcfc7728718d13d027b1a8fe6426a73b775a9170371060381b139
  simulator_log_sha256: 2341b8caa80e749ad9a6e224924adc28ad10a93ed8d73a94e5b1bc54b3ff2304
  moveit_log_sha256: 5a6a732d5e2d471ac334504141cfd46beef649495a8a4a54d4b81c17e8ddfc85
decision: Do not count this run. Add only a 50 ms bilateral-contact loss guard to transport, preserve immediate force/pause/epoch/table-support failures, ResetWorld, and rerun the whole cycle.
```

## Checkpoint CP-155

```yaml
checkpoint_id: CP-155
checkpoint_time: 2026-08-12T05:12:11+08:00
last_valid_experiment: EXP-120 VALID behavioral failure
current_hypothesis: A 50 ms sustained bilateral-contact loss guard filters the single contact-manifold handoff while still aborting any real grasp loss before the next physical phase.
working_tree_status: Same intentional Task 13/14 source/model/plan/ledger/fork state. Protected Gazebo status remains clean. Simulator is epoch 4 running at the completed transport endpoint with physical bilateral grasp and MoveIt collision shadow attached.
confirmed_conclusions:
  - Corrected current-epoch gates passed the entire remaining lift and four transport waypoints.
  - Waypoint 5 physically completed; failure was an observer false abort after lower-layer success, not planning, controller, force, support, or grasp failure.
  - Full-cycle acceptance still requires a fresh reset and uninterrupted rerun.
next_command: Preregister and execute one qualified epoch 4 -> 5 ResetWorld, then rebuild epoch-5 scripts with the bounded transport guard.
```

## Experiment EXP-121

```yaml
experiment_id: EXP-121
prior_experiment: EXP-120 VALID transport-monitor failure
status: RUNNING
lifecycle: QUALIFIED_RESETWORLD_AFTER_TRANSPORT_MONITOR_FAILURE
run_mode: one_task_start_transaction_then_attachment_clean_scene_restore
hypothesis: The qualified ResetWorld boundary recovers the held transport endpoint to clean paused epoch-5 task_start.
single_variable: Execute only one unchanged ResetWorld(task_start) transaction and exact formal Planning Scene restore.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 4
  expected_new_reset_epoch: 5
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_script: [/tmp/so101_exp121_reset.py, dce89d726720d515293be1e808fd4b00ba026f7b5bebdbd62f1eded464574fb2]
preconditions:
  - Same owned epoch-4 stack is running at the physically completed transport endpoint with active controllers and attached collision shadow.
  - EXP-120 terminal electronic/log evidence is captured; reset script passes Ruff, pycompile, and SHA verification.
success_criteria:
  - Receipt exactly 4 -> 5 at step 0; final paused task_start object/joints, active controllers, exact world scene/colors, and empty attachment list satisfy unchanged gates.
failure_criteria: Any reset, joint, object, controller, scene, provenance, or cleanup mismatch blocks the rerun.
invalid_criteria: Any unregistered motion, process restart, model/config change, direct state write, or simulator constraint invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh epoch-5 full cycle with bounded transport contact guard only after VALID reset.
```

## Experiment EXP-122 Terminal Result

```yaml
experiment_id: EXP-122
status: VALID
terminal_result: QUALIFIED_ORDERED_SNAPSHOT_RESET_AND_VISUAL_ACCEPTANCE
terminal_time: 2026-08-12T05:17:00+08:00
command: python3 /tmp/so101_exp122_reset.py
exit_code: 0
result:
  reset_receipt: {old_epoch: 4, new_epoch: 5, simulation_step: 0, keyframe: task_start}
  final_paused: true
  controllers_active: true
  final_cup_position_m: [0.02, -0.28, 0.165]
  planning_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_attached_object_ids: []
visual_acceptance:
  rviz_left_mujoco_right: true
  horizontal_task_start_arm: true
  open_gripper_clear_of_upright_cup: true
  complete_scene_and_target_ring_visible: true
  viewer_pause_visible: true
evidence:
  reset_json_sha256: c117c1731a54daefc004e990496e922b99437023113a3a51ac7b8af3252f79d8
  reset_log_sha256: 7aced85c2df459cbbf4892b401ffdb3eda2c3ab1d31e1ff1d724cf8d58d9bc2b
  post_reset_cua_sha256: 227ff5c357649e2cc1383114ca7125f112aa5d146de4c503dba5afa8955aa326
decision: Ordered fresh-client ResetWorld is qualified electronically and visually. Begin a fresh epoch-5 full cycle.
```

## Checkpoint CP-157

```yaml
checkpoint_id: CP-157
checkpoint_time: 2026-08-12T05:18:00+08:00
last_valid_experiment: EXP-122 VALID qualified reset
current_hypothesis: The final missing transport monitor grace aligns transport with the already qualified contact-manifold semantics and permits one uninterrupted full success.
working_tree_status: Intentional Task 13/14 reset/scene/phase changes remain. Protected Gazebo status is clean. Simulator is paused at exact epoch-5 task_start with active controllers and clean formal scene.
confirmed_conclusions:
  - ResetWorld has now recovered two real held-object failures and is visually repeatable.
  - EXP-123 changes only transport bilateral-contact loss from instantaneous abort to 50 ms sustained loss; pause/epoch, force, and table-contact failures remain immediate.
  - All epoch-5 scripts pass Ruff, pycompile, provenance scan, and SHA matching.
next_command: Preregister and execute one uninterrupted epoch-5 full physical pick-place.
```

## Experiment EXP-123

```yaml
experiment_id: EXP-123
prior_experiment: EXP-122 VALID qualified reset
status: RUNNING
lifecycle: FULL_PHYSICAL_PICK_PLACE_WITH_BOUNDED_CONTACT_AND_ALIGNMENT
run_mode: one_uninterrupted_epoch_5_staged_cycle
hypothesis: A 50 ms transport contact-loss guard filters the observed single-frame handoff while all real physical failures remain bounded, allowing the qualified cycle to place the cup stably inside the target.
single_variable: Add only SustainedConditionGuard(0.05) to bilateral contact loss in transport. Motion targets, force limits, pause/epoch gates, table-contact gate, alignment, release, scene, model, and phase order remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 5
  initial_state: EXP-122 visually accepted paused task_start with clean scene
  policy_sha256: 6b741dc8a73f8e1845b3ba6f6c20196b691364294cd0023a0c33c7a33766375a
  staged_approach_sha256: 70f76ef452976dcf6176f4559061822505e39baad1f465b6c02f5620222d6588
  orchestration_script: [/tmp/so101_exp123_run.bash, 3ce015603fd4877890d1ba3a1572855270e5fc09006e4dec94d8387ac5da8b54]
  phase_scripts:
    - [/tmp/so101_exp123_contact_hold.py, 4db8501a1407d95adf4fe8359af6ad9cedf95ada47242a12175efa34a846c6bb]
    - [/tmp/so101_exp123_micro_lift.py, 0c2d05271d5986687328c074ba8fe741ebe353e7475d473f1d57d7287e90a07b]
    - [/tmp/so101_exp123_policy_lift_waypoint1.py, b0f2253a02836d771e9817c02608244d36195adab29a0fb85e1ad62107c6e0fe]
    - [/tmp/so101_exp123_remaining_lift.py, ed68495b6aae46249a3a652c695c2435c3c2c0f8fc9651908de99044179c9a06]
    - [/tmp/so101_exp123_transport.py, f71921c0cd0124864dc73fae9de4f723227a362ed4efa79fb3c8a655ed9b371b]
    - [/tmp/so101_exp123_descend.py, 4ccdb8c5e4a367e91cd3b447735e32e44b4c9d1db5bd9d35663c3808bfeefd00]
    - [/tmp/so101_exp123_place_alignment.py, 6d8cf2a71ce865a20e481d72315a0527f0a389c39783fe5f1dc45cdc4ec5e889]
    - [/tmp/so101_exp123_release_retreat.py, 5655f476ba78ec435bbf934fbee4638578872f4db054c6a6cdc8c425f03f5418]
  transport_contact_loss_grace_s: 0.05
  place_alignment_target_m: [-0.0788, -0.2475, 0.1835]
  place_alignment_tolerance_m: 0.003
  place_alignment_max_attempts: 3
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
preconditions:
  - Same owned epoch-5 stack is paused at task_start, controllers active, no attached object, exact scene and visual evidence accepted.
  - Scripts are Ruff/pycompile/SHA clean; no state action after preregistration.
success_criteria:
  - All phases complete in order without reset/pause/process restart/direct state write/simulator attachment/unbounded retry.
  - Physical bilateral grasp stays within force/contact gates through lift, transport, descend, and alignment.
  - Unconstrained release settles upright and table-supported inside unchanged target for at least five fresh stable samples over 0.20 s.
  - Final Planning Scene contains exact world geometry/colors and no attached object; final gripper contact is zero.
  - Passive CUA shows RViz left, Viewer right, cup inside red ring, and arm retreated.
failure_criteria: Any phase, planning, execution, convergence, sustained contact, force, support, alignment, placement, scene, provenance, or visual gate failure stops immediately.
invalid_criteria: Any reset/pause after resume, direct object write, teleport, simulator constraint/attachment, model/config mutation, process restart, missing evidence, or unregistered retry invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Diagnose only first failure, or record first full-cycle success and proceed to production runner/gates.
```

## Experiment EXP-121 Terminal Result

```yaml
experiment_id: EXP-121
status: VALID
terminal_result: BEHAVIORAL_FAILURE_QUEUED_RUNNING_FRAME_ACCEPTED_AFTER_PAUSE_SNAPSHOT_REQUEST
terminal_time: 2026-08-12T05:14:00+08:00
command: python3 /tmp/so101_exp121_reset.py
exit_code: 1
result:
  reset_world_called: false
  reset_epoch_unchanged: 4
  terminal_paused: true
  controllers_active_after_failure: [arm_controller, gripper_controller]
  error: ResetFailed reset transaction error switch controllers service timeout
diagnosis:
  - Initial acquisition requested pause(true), but accepted one queued pre-pause Running evidence frame before the authoritative paused frame arrived.
  - It therefore skipped prepare-running and requested strict controller deactivation while the control loop was actually paused; controller_manager timed out after 5 seconds.
  - Fail-closed behavior preserved epoch 4, active controllers, grasped cup, and paused physics; ResetWorld was never called.
decision: Require paused=true after any active initial snapshot request, while still accepting an immediately available fresh frame without service action. Add queued-running regression coverage, rebuild, and retry.
```

## Checkpoint CP-156

```yaml
checkpoint_id: CP-156
checkpoint_time: 2026-08-12T05:16:02+08:00
last_valid_experiment: EXP-121 VALID behavioral failure
current_hypothesis: Waiting past queued Running evidence until the requested paused frame arrives guarantees resume-before-deactivate ordering and prevents switch timeout.
working_tree_status: Intentional Task 13/14 changes plus ordered initial snapshot acquisition. Protected Gazebo status remains clean. Simulator remains paused at epoch 4, controllers active, physical cup held, stale MoveIt attachment present.
confirmed_conclusions:
  - Modified regression test failed before the fix because operations were pause(true), deactivate instead of pause(true), pause(false), deactivate.
  - Client now accepts any immediately fresh frame before service action, but after requesting pause it ignores same-session frames until paused=true.
  - All 22 reset tests, Ruff, and rebuild pass. Reset source SHA is 4149260ad44e47b45d47576a17bf2132af9e86a668122ff7c41cbfec8c2212f2; test SHA is 218c5f7565e744f13b183ecb6b581c3ce2f6aa3d7349890853ca7218fa37c921.
next_command: Preregister and execute EXP-122 on the preserved epoch-4 paused state.
```

## Experiment EXP-122

```yaml
experiment_id: EXP-122
prior_experiment: EXP-121 VALID ordered-snapshot failure
status: RUNNING
lifecycle: ORDERED_PAUSED_SNAPSHOT_RESETWORLD_REQUALIFICATION
run_mode: requested_paused_snapshot_then_reset_and_attachment_clean_scene_restore
hypothesis: Ignoring queued Running evidence after pause request yields resume-before-deactivate ordering and a qualified epoch 4 -> 5 reset.
single_variable: Require paused=true only after an initial snapshot request. Reset, controllers, scene, model, geometry, keyframe, session, and thresholds remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 4
  expected_new_reset_epoch: 5
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py, 4149260ad44e47b45d47576a17bf2132af9e86a668122ff7c41cbfec8c2212f2]
  reset_test: [src/so101_mujoco_demo_py/test/test_mujoco_reset.py, 218c5f7565e744f13b183ecb6b581c3ce2f6aa3d7349890853ca7218fa37c921]
  reset_script: [/tmp/so101_exp122_reset.py, 3346375088bdab7350abda23b4704adb8360a57cbc1c654a28d41a7f592d75c9]
preconditions:
  - Same epoch-4 stack remains paused after EXP-121, controllers active, cup physically held, stale collision shadow attached.
  - Tests, Ruff, build, pycompile, hashes, and protected Gazebo check pass.
success_criteria:
  - Ordered acquisition resumes before strict deactivation; receipt exactly 4 -> 5 at step 0.
  - Final paused task_start object/joints, active controllers, exact world geometry/colors, and empty attachment list satisfy unchanged gates.
failure_criteria: Any acquisition, controller ordering, reset, convergence, scene cleanup, or provenance mismatch blocks the full cycle.
invalid_criteria: Any unregistered action, process restart, model/config mutation, direct state write, or simulator constraint invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh epoch-5 full cycle with bounded transport contact guard only after VALID reset.
```

## Experiment EXP-118 Terminal Result

```yaml
experiment_id: EXP-118
status: VALID
terminal_result: PRE_ACTION_FAILURE_REDUNDANT_INITIAL_JOINT_WAIT_IN_TEST_WRAPPER
terminal_time: 2026-08-12T05:05:00+08:00
command: python3 /tmp/so101_exp118_reset.py
exit_code: 1
result:
  reset_client_called: false
  reset_world_called: false
  physical_state_unchanged: true
  error: RuntimeError initial joint state unavailable
diagnosis:
  - The experimental wrapper still waited for pre-reset joint feedback, but a fresh subscriber receives no historical joint sample while the simulator is paused.
  - The production transaction does not require pre-reset joints; after acquiring provenance it resumes and explicitly requires a new post-reset joint callback before convergence.
decision: Remove only the redundant wrapper precondition. Keep every production post-reset joint freshness and convergence gate unchanged.
```

## Checkpoint CP-153

```yaml
checkpoint_id: CP-153
checkpoint_time: 2026-08-12T05:06:25+08:00
last_valid_experiment: EXP-118 VALID pre-action failure
current_hypothesis: Directly invoking the rebuilt production reset client is sufficient to acquire paused provenance, resume for fresh joints, reset, converge, re-pause, and restore the scene.
working_tree_status: Same intentional Task 13/14 state; no source change after CP-152. Protected Gazebo status remains clean. Simulator remains paused at epoch 3 with stale MoveIt attachment.
confirmed_conclusions:
  - EXP-118 never called the production reset client and therefore did not test the new behavior.
  - EXP-119 wrapper has no pre-evidence or pre-joint reads; it delegates initial acquisition and all convergence to MujocoResetClient.
next_command: Preregister and execute EXP-119 on the unchanged epoch-3 paused state.
```

## Experiment EXP-119

```yaml
experiment_id: EXP-119
prior_experiment: EXP-118 VALID wrapper pre-action failure
status: RUNNING
lifecycle: DIRECT_FRESH_PAUSED_CLIENT_RESETWORLD_REQUALIFICATION
run_mode: direct_production_reset_then_attachment_clean_scene_restore
hypothesis: Direct invocation of the rebuilt reset client acquires epoch-3 paused provenance, resets to epoch 4, obtains fresh joints, and removes the stale Planning Scene attachment.
single_variable: Delete only the wrapper's redundant pre-reset joint wait. Production code and all frozen EXP-118 inputs remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 3
  expected_new_reset_epoch: 4
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_source_sha256: bf78b0eed961092835ee9c82e8f8c22c6a4dfe1fff7f4d4a39f9c3949b35009d
  scene_setup_source_sha256: 4125cbb3ba87222bca9323572d6e3d1d381d503acc50261e7b20a136947fc66f
  reset_script: [/tmp/so101_exp119_reset.py, 9e9be8ccf4596c8a3330d7272ac3edb76997dbdf195157bba0af68c26f3f26ef]
preconditions:
  - Same fresh client condition: simulator paused at epoch 3, no replayable evidence or joint history, stale attached plastic_cup present.
  - Reset and scene tests pass; overlay rebuilt; wrapper Ruff and pycompile pass; hashes match.
success_criteria:
  - Receipt exactly 3 -> 4 at step 0; final paused task_start object/joints and active controllers satisfy unchanged thresholds.
  - Planning Scene contains exact world geometry/colors and no attached object.
  - Passive CUA proves task_start arm/open gripper/original upright cup/complete scene/visible PAUSE with RViz left and Viewer right.
failure_criteria: Any acquisition, reset, joint freshness, convergence, scene cleanup, provenance, or visual mismatch blocks the full cycle.
invalid_criteria: Any unregistered action, process restart, model/config change, direct state write, simulator constraint, or missing visual evidence invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh full-cycle attempt at epoch 4 only after VALID reset and visual acceptance.
```

## Experiment EXP-128

```yaml
experiment_id: EXP-128
prior_experiment: EXP-127 VALID final-out-of-region failure
status: RUNNING
lifecycle: QUALIFIED_RESETWORLD_AFTER_PHYSICAL_RELEASE_PLACEMENT_MISS
run_mode: one_task_start_transaction_then_attachment_clean_scene_restore
hypothesis: The qualified ResetWorld boundary recovers the released epoch-6 scene to exact paused epoch-7 task_start before the compensated full-cycle rerun.
single_variable: Execute only one unchanged ResetWorld(task_start) transaction and exact formal Planning Scene restore. The newly built placement compensation is not exercised during reset.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 6
  expected_new_reset_epoch: 7
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py, 4149260ad44e47b45d47576a17bf2132af9e86a668122ff7c41cbfec8c2212f2]
  scene_setup_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/scene_setup.py, 4125cbb3ba87222bca9323572d6e3d1d381d503acc50261e7b20a136947fc66f]
  reset_script: [/tmp/so101_exp128_reset.py, d8735015d0ce340d1d51e17d00984d8959a2ba1771aba0964ce0a277f7c748d8]
preconditions:
  - Same epoch-6 stack remains running after EXP-127, controllers active, cup physically released and stable on the table, no gripper contact, and no MoveIt attachment.
  - Reset tests, Ruff, build, script pycompile/hash, and protected Gazebo check pass.
success_criteria:
  - Receipt exactly 6 -> 7 at step 0; final paused task_start object/joints and active controllers satisfy unchanged thresholds.
  - Planning Scene contains exact table, pedestal, 13-primitive cup geometry/colors and no attached object.
  - Passive CUA proves horizontal task_start arm, open gripper, original upright cup, complete scene, red target ring, RViz left, Viewer right, and visible PAUSE.
failure_criteria: Any reset, joint, object, controller, scene, provenance, or visual mismatch blocks the rerun.
invalid_criteria: Any unregistered motion, process restart, model/config mutation, direct state write, or simulator constraint invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh epoch-7 full physical cycle with the frozen measured settling compensation only after VALID electronic and visual reset.
```

## Experiment EXP-128 Terminal Result

```yaml
experiment_id: EXP-128
status: VALID
terminal_result: QUALIFIED_RESETWORLD_AND_VISUAL_ACCEPTANCE
terminal_time: 2026-08-12T05:37:00+08:00
command: python3 /tmp/so101_exp128_reset.py
exit_code: 0
result:
  reset_receipt: {old_epoch: 6, new_epoch: 7, simulation_step: 0, keyframe: task_start}
  final_paused: true
  controllers_active: true
  final_joint_positions_rad: [2.0106801636346586e-08, 9.11352966981906e-05, 8.220945026002406e-05, 7.552795673726909e-06, 2.240418047689964e-09, -6.07537537969906e-08]
  final_cup_position_m: [0.02, -0.28, 0.165]
  planning_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_attached_object_ids: []
visual_acceptance:
  rviz_left_mujoco_right: true
  horizontal_task_start_arm: true
  open_gripper_clear_of_upright_original_cup: true
  complete_scene_and_red_target_ring_visible: true
  viewer_pause_and_status_paused_visible: true
evidence:
  reset_json_sha256: 0398783829e0f17a1a54d2b7bc6307b39eb118704ab5ac8876fa3cd90c7afcb6
  reset_log_sha256: dcb028a78b817600e0a7e1dc3b51f0c3ad287d1e508e070e8127366d52ce9d49
  post_reset_cua_sha256: f8d838206694bac86a58214dc106f899a3e5a3ca36094cd0b7d511405eab02e8
decision: ResetWorld is qualified across physics, controllers, joint state, reset evidence, Planning Scene, and visible GUI. Proceed to one fresh epoch-7 full cycle.
```

## Checkpoint CP-159

```yaml
checkpoint_id: CP-159
checkpoint_time: 2026-08-12T05:37:00+08:00
last_valid_experiment: EXP-128 VALID qualified reset
current_hypothesis: The frozen +0.0150 m pre-release y compensation moves the post-release settled cup into the unchanged target region while all already qualified phase gates remain intact.
working_tree_status: Intentional Task 13/14 changes. Protected Gazebo package remains clean. Simulator is paused at exact epoch-7 task_start with active controllers and clean formal scene.
next_command: Generate epoch-7 scripts, lint/compile/provenance-scan/hash them, preregister EXP-129, then execute once without interruption.
```

## Experiment EXP-129

```yaml
experiment_id: EXP-129
prior_experiment: EXP-128 VALID qualified reset
status: RUNNING
lifecycle: FULL_PHYSICAL_PICK_PLACE_WITH_MEASURED_SETTLING_COMPENSATION
run_mode: one_uninterrupted_epoch_7_staged_cycle
hypothesis: Applying the measured +0.0150 m pre-release y compensation places the unconstrained settled cup inside the unchanged final target after physical release and collision-checked retreat.
single_variable: Change only MuJoCo place settling compensation y from +0.0025 m to +0.0150 m based on EXP-127 measured -0.014982 m settling shift. Final target bounds, phase sequence, motion targets except pre-release alignment, force/contact/stability thresholds, controller path, scene geometry, and model remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 7
  initial_state: EXP-128 electronically and visually accepted paused task_start with clean formal scene
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, bc06bd8afd4936ca05653c19f720c5f2e2db339eb34bc4a426b4a1a2ba513205]
  staged_approach_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/staged_approach.py, 06e3b30ba0830e058eff42bd06010f842e57a9155729e148520bf414e4367a18]
  orchestration_script: [/tmp/so101_exp129_run.bash, 23487abae8a54d0ddaca6e8d7c31174db2e25016f45982070017c6ad0bee2fd5]
  phase_scripts:
    - [/tmp/so101_exp129_contact_hold.py, 8f154dfb7da9dd0e02c8a39a087bf4cd8e602c8c8620773bb0f2b27e2d14bf5d]
    - [/tmp/so101_exp129_micro_lift.py, 0d0280141e9fb76b223ec042b8183b55a69c19ba3abaa841fac326df60ca0c08]
    - [/tmp/so101_exp129_policy_lift_waypoint1.py, 9552f3cc430a0dc741665bf6090d8c21809edf93b9bddcc9b0887c1e8a608cb2]
    - [/tmp/so101_exp129_remaining_lift.py, 6aeb720d48c30efdbef87655e48d97918bb2f17701911cef1da836c5014d49ec]
    - [/tmp/so101_exp129_transport.py, 07dc4154ef2e05245fecefe457cba5d953167f32a7e5c7be67b9d9b806564493]
    - [/tmp/so101_exp129_descend.py, 03ffe68d17849060bd5f42c20f9825327fc76f00b95c0d21aebcfacbae7400e8]
    - [/tmp/so101_exp129_place_alignment.py, 0f468623d788909a54aa23717582f27b1eda908a0a047910fb6b31d97770d0a5]
    - [/tmp/so101_exp129_release_retreat.py, efb7f8cc75850a79887eed5d43c443b613da7a64b7d7efe5e828b1aa17e3a567]
  transport_velocity_acceleration_scaling: 0.05
  transport_contact_loss_grace_s: 0.05
  place_xyz_m: [-0.080, -0.250, 0.165]
  place_settling_compensation_m: [0.0012, 0.0150, 0.0185]
  pre_release_target_m: [-0.0788, -0.2350, 0.1835]
  place_alignment_tolerance_m: 0.003
  place_alignment_max_attempts: 3
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
preconditions:
  - Same epoch-7 stack remains paused at exact task_start, controllers active, attachment-free exact Planning Scene, and EXP-128 CUA evidence accepted.
  - All scripts pass Bash syntax, Ruff, pycompile, forbidden-action provenance scan, SHA matching, and protected Gazebo isolation check.
success_criteria:
  - All phases complete in order without reset, pause after resume, process restart, direct object state write, simulator attachment, teleport, or unbounded retry.
  - Physical bilateral grasp remains within force/contact/support gates through micro-lift, policy lift, transport, descend, and bounded alignment.
  - q6 physically opens; the unconstrained cup settles upright and table-supported inside unchanged target bounds for at least five fresh stable samples over 0.20 s.
  - Three MoveIt-planned retreat waypoints finish, both fingertip contact counts become zero, and the final Planning Scene has exact world geometry/colors and no attachment.
  - Passive CUA shows RViz left, Viewer right, cup visibly inside the red target ring, arm retreated, complete scene, and Viewer Running.
failure_criteria: Any phase, planning, execution, convergence, contact, force, support, alignment, placement, scene, provenance, or visual gate failure stops immediately and is retained.
invalid_criteria: Any reset/pause after resume, direct object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, model/config mutation, process restart, missing evidence, or unregistered retry invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: On success, capture passive CUA and formalize production runner. On failure, diagnose only the first failure before any next state action.
```

## Experiment EXP-129 Terminal Result

```yaml
experiment_id: EXP-129
status: VALID
terminal_result: BEHAVIORAL_FAILURE_FIXED_JOINT_RETREAT_SWEEPS_RELEASED_CUP_OUT_OF_TARGET
terminal_time: 2026-08-12T05:42:25+08:00
command: bash /tmp/so101_exp129_run.bash
exit_code: 1
completed_phases:
  - staged_approach_15_waypoints
  - bilateral_contact_hold_168_samples
  - physical_micro_lift
  - policy_lift_5_waypoints
  - transport_5_waypoints
  - descend_3_waypoints
  - bounded_place_alignment_1_attempt
  - physical_q6_release
  - retreat_3_waypoints
  - detach_and_world_scene_sync
failure:
  phase: final placement evaluation after retreat
  code: FINAL_OUT_OF_REGION
  pre_release_cup_position_m: [-0.0796618373785821, -0.23296885133827266, 0.18409645994095847]
  free_released_cup_position_m: [-0.07984725866953395, -0.23331722112065933, 0.16491956762291168]
  free_released_contacts: {left: 0, right: 0, table: true}
  retreat_waypoint_1_cup_position_m: [-0.07910846769998967, -0.26084658626364815, 0.1652335437602212]
  retreat_waypoint_1_contacts: {left: 1, right: 0, table: true}
  final_cup_position_m: [-0.07938639767784889, -0.261368301573421, 0.16507549445788602]
  final_contacts: {left: 0, right: 0, table: true}
  final_upright_tilt_rad: 0.006867942443317374
  target_x_bounds_m: [-0.085, -0.075]
  target_y_bounds_m: [-0.255, -0.245]
diagnosis:
  - The +0.0150 m pre-release y compensation was correctly executed, but free release changed y by only -0.000348 m and was stable with zero fingertip contact.
  - Fixed RETREAT waypoint 1 then undid the alignment correction and swept the left fingertip through the cup, moving it -0.027529 m in y; the terminal left contact count was 1.
  - Therefore the prior 15 mm estimate conflated free settling with retreat-induced contact. More alignment compensation is invalid; the root cause is the post-alignment fixed-joint retreat path.
  - The latest Gazebo implementation already solves the same geometry by a bounded 10 mm radial TCP separation away from the observed cup, followed by a 60 mm world-z lift. The MuJoCo package must independently implement that formal outcome-first retreat without changing the protected Gazebo package.
evidence:
  master_log_sha256: d3f65f534a4c79352403c46e13d49c015332cecaf992ae8e5b3395f500859d94
  release_retreat_json_sha256: 36c8bfa96ee9a65655a1629e4dca9e6d1914c9df0dfc888460ba3dd065aef033
  release_retreat_log_sha256: d14f77de044b4f9ce405cc728c403fd9bccea2401c8d29eada12b75edd98e50a
  place_alignment_json_sha256: 61c9536697bab2e66a10fd326417464ed46c0610d3739b8c2df7aae58105206e
  transport_json_sha256: e5a070cd4362e4d6c839d1544a080ab0b4b35a75a27c41fe5cb31b92fc894f83
decision: Do not count. Revert the disproved y compensation to +0.0025 m, add bounded radial TCP separation plus vertical lift before any joint-space retreat, require zero fingertip contact throughout separation, then qualified-reset and rerun from task_start.
```

## Checkpoint CP-160

```yaml
checkpoint_id: CP-160
checkpoint_time: 2026-08-12T05:43:49+08:00
last_valid_experiment: EXP-129 VALID retreat-contact failure
current_hypothesis: Outcome-first task-space separation after the stable zero-contact release prevents the aligned gripper from re-entering the cup; the original +0.0025 m y compensation already places the freely released cup inside the unchanged target.
working_tree_status: Intentional Task 13/14 changes. Protected Gazebo status is clean. Simulator remains epoch 7 running after release/retreat, cup stable outside target, no fingertip contact, scene detached/synced.
next_command: Add a MuJoCo-owned tested release-separation policy/helper, revert only the disproved compensation, rebuild, then preregister ResetWorld before changing physical state.
```

## Checkpoint CP-161

```yaml
checkpoint_id: CP-161
checkpoint_time: 2026-08-12T05:47:00+08:00
last_valid_experiment: EXP-129 VALID retreat-contact failure
current_hypothesis: The opened gripper must separate in task space using the observed TCP-to-cup radial direction before lifting, rather than returning to pre-alignment joint waypoints.
production_change:
  module: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/release_retreat.py, bf5fbb5573b9c2711d715f0dfc5fa7fa47db04ba21697bf8409fc490c30f7b40]
  test: [src/so101_mujoco_demo_py/test/test_release_retreat.py, 8690303ccb8a31ea9d23e01f7ed0bab181251a94c7c399778ee510fe616b224f]
  place_test: [src/so101_mujoco_demo_py/test/test_place_alignment.py, 87f93d3c4fe5835aad30964cfb6a3ff609745b10ab020576e3ceadb720e5d4a9]
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, 9867a31f013a5556231e46c05d38972809e06de6d1960145b95a9cd6b134145c]
  place_settling_compensation_m: [0.0012, 0.0025, 0.0185]
  release_retreat:
    radial_separation_m: 0.010
    vertical_clearance_m: 0.060
    orientation_tolerance_rad: 0.15
    position_tolerance_m: 0.001
    velocity_scaling: 0.03
    acceleration_scaling: 0.03
verification:
  tdd_red: test collection failed because so101_mujoco_demo_py.release_retreat did not exist
  tdd_green: 13 passed
  ruff: passed
  overlay_build: passed
  protected_gazebo_status: clean
next_command: Execute exactly one preregistered ResetWorld epoch 7 to 8 before the fresh full-cycle validation.
```

## Experiment EXP-130

```yaml
experiment_id: EXP-130
prior_experiment: EXP-129 VALID retreat-contact failure
status: RUNNING
lifecycle: QUALIFIED_RESETWORLD_AFTER_RETREAT_CONTACT_FAILURE
run_mode: one_task_start_transaction_then_attachment_clean_scene_restore
hypothesis: The qualified ResetWorld boundary recovers the released epoch-7 scene to exact paused epoch-8 task_start before testing the new outcome-first retreat.
single_variable: Execute only one unchanged ResetWorld(task_start) transaction and exact formal Planning Scene restore. The new release-retreat policy is not exercised during reset.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  expected_old_reset_epoch: 7
  expected_new_reset_epoch: 8
  keyframe: task_start
  expected_joint_positions_rad: [0, 0, 0, 0, 0, 0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  expected_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  reset_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py, 4149260ad44e47b45d47576a17bf2132af9e86a668122ff7c41cbfec8c2212f2]
  scene_setup_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/scene_setup.py, 4125cbb3ba87222bca9323572d6e3d1d381d503acc50261e7b20a136947fc66f]
  reset_script: [/tmp/so101_exp130_reset.py, 596dbee7e433281b54fb52bb80eeee2220730af207a7529536ce6322aca9a35d]
preconditions:
  - Same epoch-7 stack remains running after EXP-129, controllers active, cup physically released and stable on the table, no fingertip contact, and no MoveIt attachment.
  - Reset tests, Ruff, build, script pycompile/hash, and protected Gazebo check pass.
success_criteria:
  - Receipt exactly 7 -> 8 at step 0; final paused task_start object/joints and active controllers satisfy unchanged thresholds.
  - Planning Scene contains exact table, pedestal, 13-primitive cup geometry/colors and no attached object.
  - Passive CUA proves horizontal task_start arm, open gripper, original upright cup, complete scene, red target ring, RViz left, Viewer right, and visible PAUSE.
failure_criteria: Any reset, joint, object, controller, scene, provenance, or visual mismatch blocks the rerun.
invalid_criteria: Any unregistered motion, process restart, model/config mutation, direct state write, or simulator constraint invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Fresh epoch-8 full physical cycle with tested task-space separation only after VALID electronic and visual reset.
```

## Experiment EXP-130 Terminal Result

```yaml
experiment_id: EXP-130
status: VALID
terminal_result: QUALIFIED_RESETWORLD_AND_VISUAL_ACCEPTANCE
terminal_time: 2026-08-12T05:49:00+08:00
command: python3 /tmp/so101_exp130_reset.py
exit_code: 0
result:
  reset_receipt: {old_epoch: 7, new_epoch: 8, simulation_step: 0, keyframe: task_start}
  final_paused: true
  controllers_active: true
  final_joint_positions_rad: [5.179811209889032e-08, 0.0002673190668043892, 0.0002364111460597401, 2.530913097659213e-05, 5.760706345855852e-09, -1.5631363299656996e-07]
  final_cup_position_m: [0.02, -0.28, 0.165]
  planning_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_attached_object_ids: []
visual_acceptance:
  rviz_left_mujoco_right: true
  horizontal_task_start_arm: true
  open_gripper_clear_of_upright_original_cup: true
  complete_scene_and_red_target_ring_visible: true
  viewer_pause_and_status_paused_visible: true
evidence:
  reset_json_sha256: f0ef3ed683f2b4f865d8776021ae27850b51f75dbce11349de8dee3b587cba08
  reset_log_sha256: 77125658514bd212171d70046ab69e922cdbcb053f2930aef4d479b8294bc828
  post_reset_cua_sha256: 54a9c116359e9c317ed47ee07bc3f094d4605caa229dc112d6a373906bf4e320
decision: ResetWorld is qualified electronically and visually. Proceed to one fresh epoch-8 full cycle with the tested outcome-first retreat.
```

## Checkpoint CP-162

```yaml
checkpoint_id: CP-162
checkpoint_time: 2026-08-12T05:49:00+08:00
last_valid_experiment: EXP-130 VALID qualified reset
current_hypothesis: Stable zero-contact free release at the original compensated target, followed by radial separation and vertical lift, will preserve the cup inside the unchanged red-ring target.
working_tree_status: Intentional Task 13/14 changes plus MuJoCo-owned release-retreat helper/tests/config. Protected Gazebo remains clean. Simulator is paused at exact epoch-8 task_start with active controllers and clean scene.
next_command: Freeze/lint/hash epoch-8 full-cycle scripts, preregister EXP-131, then execute once without interruption.
```

## Experiment EXP-131

```yaml
experiment_id: EXP-131
prior_experiment: EXP-130 VALID qualified reset
status: RUNNING
lifecycle: FULL_PHYSICAL_PICK_PLACE_WITH_OUTCOME_FIRST_TASK_SPACE_RETREAT
run_mode: one_uninterrupted_epoch_8_staged_cycle
hypothesis: The original free-settling compensation places the released cup inside the unchanged target; detaching the MoveIt shadow immediately, then moving the opened gripper 10 mm radially away and 60 mm upward with zero fingertip contact preserves that valid physical outcome.
single_variable: Replace the post-alignment fixed-joint retreat with two bounded pose-planned task-space segments and revert the disproved y compensation from +0.0150 m to +0.0025 m. All pre-release phases, final target bounds, force/contact/stability thresholds, model, controller path, and scene geometry remain unchanged.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 8
  initial_state: EXP-130 electronically and visually accepted paused task_start with clean formal scene
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, 9867a31f013a5556231e46c05d38972809e06de6d1960145b95a9cd6b134145c]
  release_retreat_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/release_retreat.py, bf5fbb5573b9c2711d715f0dfc5fa7fa47db04ba21697bf8409fc490c30f7b40]
  staged_approach_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/staged_approach.py, 06e3b30ba0830e058eff42bd06010f842e57a9155729e148520bf414e4367a18]
  orchestration_script: [/tmp/so101_exp131_run.bash, 642828998b8687c85425884b8e48a2613d1e9443ff7bda667f9ad8cf0f690736]
  phase_scripts:
    - [/tmp/so101_exp131_contact_hold.py, f0407778053d27a4235910c4333bed243e7b59cc3cd5dbce54ea4b4e70f7f050]
    - [/tmp/so101_exp131_micro_lift.py, cf25cbe67a9b55f606d79f7dbacfcd97c36e5a8b5417cd072814d792f82cd50b]
    - [/tmp/so101_exp131_policy_lift_waypoint1.py, 23049fcb071263e64bb3291fe06f03be06881eb0df8bd053375c851c2b072b3c]
    - [/tmp/so101_exp131_remaining_lift.py, 1662ecdde0000487438dc978fbeb07477108b206587ea1d650b4ba420fe4a709]
    - [/tmp/so101_exp131_transport.py, ae2514d21325b41c186600130dd593fab0f7b15b73ff8bc837a2d5b4f236d061]
    - [/tmp/so101_exp131_descend.py, af87faeaf5770c20c307e4f11a9ebfd131df5162149a5eca9f03af2c62b3adff]
    - [/tmp/so101_exp131_place_alignment.py, 64f64c35f4ed3b7270049b3d9ee9bae224a5336a02d54eac9d2c38a00de82ee4]
    - [/tmp/so101_exp131_release_retreat.py, 27c993860388e28f1aa854ef35e5966cbb9f4fba5095df1212898a48935d72ed]
  transport_velocity_acceleration_scaling: 0.05
  transport_contact_loss_grace_s: 0.05
  place_xyz_m: [-0.080, -0.250, 0.165]
  place_settling_compensation_m: [0.0012, 0.0025, 0.0185]
  pre_release_target_m: [-0.0788, -0.2475, 0.1835]
  release_retreat_translations:
    - radial_away_from_observed_cup_m: 0.010
    - world_z_clearance_m: 0.060
  retreat_zero_fingertip_contact_required: true
  final_target_min_xy_m: [-0.085, -0.255]
  final_target_max_xy_m: [-0.075, -0.245]
preconditions:
  - Same epoch-8 stack remains paused at exact task_start, controllers active, attachment-free exact Planning Scene, and EXP-130 CUA evidence accepted.
  - Production policy/helper tests pass 13/13; all scripts pass Bash syntax, Ruff, pycompile, forbidden-action provenance scan, SHA matching, and protected Gazebo isolation.
success_criteria:
  - Every phase completes in order without reset, pause after resume, process restart, direct object state write, simulator attachment, teleport, or unbounded retry.
  - Bilateral physical grasp remains force/contact/support-safe through lift, transport, descend, and bounded alignment.
  - q6 opens; the cup first reaches stable table support with zero fingertip contact inside the unchanged target.
  - MoveIt shadow is detached before retreat; radial and vertical pose-planned segments finish with table support and zero left/right fingertip contact throughout.
  - Final outcome passes stable upright target gates; Planning Scene contains exact synchronized world cup and no attachment.
  - Passive CUA shows RViz left, Viewer right, cup visibly inside the red target ring, arm/gripper clear above it, complete scene, and Viewer Running.
failure_criteria: Any phase, planning, execution, convergence, contact, force, support, alignment, placement, scene, provenance, or visual gate failure stops immediately and is retained.
invalid_criteria: Any reset/pause after resume, direct object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, model/config mutation, process restart, missing evidence, or unregistered retry invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: On success, capture passive CUA and promote the proven phase behavior into the production runner. On failure, diagnose only the first failure.
```

## Experiment EXP-131 Terminal Result

```yaml
experiment_id: EXP-131
status: VALID
terminal_result: PRE_RETREAT_FAILURE_ZERO_CONTACT_GATE_REJECTED_LOW_FORCE_FIXED_PAD_RESIDUAL
terminal_time: 2026-08-12T05:55:15+08:00
command: bash /tmp/so101_exp131_run.bash
exit_code: 1
completed_phases:
  - staged_approach_15_waypoints
  - bilateral_contact_hold_169_samples
  - physical_micro_lift
  - policy_lift_5_waypoints
  - transport_5_waypoints
  - descend_3_waypoints
  - bounded_place_alignment_1_attempt
  - physical_q6_release
failure:
  phase: post_release_stable_gate_before_any_retreat_motion
  error: RuntimeError stable physical state timeout
  retreat_motion_started: false
  released_q6_rad: 0.749956367645697
  released_cup_position_m: [-0.07801148852466819, -0.24742434242920178, 0.16551389665645916]
  released_cup_inside_target: true
  released_table_contact: true
  residual_contact:
    side: fixed_left_fingertip
    count: 2
    maximum_individual_force_n: 0.003019232536991923
    moving_right_contact_count: 0
  terminal_maximum_normal_force_n_including_table_n: 0.13954125284839594
diagnosis:
  - Physical release succeeded and the freely settled cup is stable inside the unchanged target before retreat.
  - Exact-zero contact is too strict at the handoff because the fixed pad can retain a harmless approximately 0.003 N manifold while the opened moving jaw is clear.
  - The outcome-first radial move is specifically intended to clear this residual. It must be allowed only at entry, force-bounded to 0.05 N, displacement-bounded to 3 mm, and required to disappear within 0.05 s; all later retreat motion still requires exact zero contact.
evidence:
  master_log_sha256: 918ef68ee3daacfdf520e385b4798889547d4d1557d0c7dcac7134915826100a
  release_retreat_json_sha256: 5cd552d42bb150d01f30083e055ad2319f230068fd629d4485bd80c16b29de4d
  release_retreat_log_sha256: 4bd41ca9628060a7d6862cf4d4ca784f5d2b9d4fe60fe85d159a2ad8e50c51a4
decision: Do not count. Preserve the released in-target state. Add explicit bounded residual-contact policy and validate radial/vertical retreat as a preregistered continuation diagnostic before reset and full rerun.
```

## Checkpoint CP-163

```yaml
checkpoint_id: CP-163
checkpoint_time: 2026-08-12T05:56:28+08:00
last_valid_experiment: EXP-131 VALID pre-retreat gate failure
current_hypothesis: A 50 ms grace for only sub-0.05 N residual fingertip contact permits radial separation to clear the fixed pad without allowing the cup to be pushed; a 3 mm cup-displacement bound detects any harmful interaction.
working_tree_status: Intentional Task 13/14 changes. Protected Gazebo remains clean. Simulator remains epoch 8 running, q6 open, cup stable inside target on table, light fixed-left-pad contact only, MoveIt shadow still attached because retreat/detach did not start.
next_command: Add tested residual-contact policy bounds, build, then preregister a no-release continuation diagnostic from the preserved epoch-8 state.
```

## Checkpoint CP-164

```yaml
checkpoint_id: CP-164
checkpoint_time: 2026-08-12T05:59:00+08:00
last_valid_experiment: EXP-131 VALID pre-retreat gate failure
current_hypothesis: A low-force, displacement-bounded residual manifold can be admitted only during the start of radial separation and must clear within 0.05 s.
production_change:
  module: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/release_retreat.py, a0c3a379fb71b25f2168e864e7499d57d835189c71836fe6d49ebcc4a6fe67f1]
  test: [src/so101_mujoco_demo_py/test/test_release_retreat.py, 723b250682b3ddb857fd22a919958b30fb170e8a8ad2eaf6ba8b26ec324c7b1c]
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808]
  residual_contact_grace_s: 0.05
  max_residual_fingertip_force_n: 0.05
  max_released_cup_displacement_m: 0.003
verification:
  tdd_red: import failed because residual_contact_within_bounds did not exist
  tdd_green: 14 passed
  ruff: passed
  overlay_build: passed
  protected_gazebo_status: clean
next_command: Execute preregistered EXP-132 from the preserved released state without reissuing q6 or any prior motion.
```

## Experiment EXP-132

```yaml
experiment_id: EXP-132
prior_experiment: EXP-131 VALID pre-retreat gate failure
status: RUNNING
lifecycle: PRESERVED_RELEASED_STATE_OUTCOME_FIRST_RETREAT_DIAGNOSTIC
run_mode: continue_from_stable_in_target_q6_open_epoch_8_state
hypothesis: The bounded radial translation clears the approximately 0.003 N fixed-pad residual within 0.05 s without moving the cup more than 3 mm; the subsequent 60 mm vertical lift remains zero-contact and preserves the cup inside target.
single_variable: Admit only the measured low-force fixed-pad residual at radial-separation entry under explicit force/displacement/grace bounds. No q6 command, reset, pause, pre-release motion, target change, model change, or simulator constraint is allowed.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 8
  initial_state:
    q6_rad: 0.749956367645697
    cup_position_m: [-0.07801148852466819, -0.24742434242920178, 0.16551389665645916]
    cup_inside_target: true
    table_contact: true
    moving_right_contact_count: 0
    fixed_left_contact_max_force_n: 0.003019232536991923
    moveit_shadow_attached: true
  diagnostic_script: [/tmp/so101_exp132_release_retreat.py, 8e3e44c48fea0fe1dad0b51d77f8d34968cf4f61f07adde8d081368036cd2a57]
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808]
  release_retreat_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/release_retreat.py, a0c3a379fb71b25f2168e864e7499d57d835189c71836fe6d49ebcc4a6fe67f1]
preconditions:
  - Same EXP-131 terminal state is preserved, running and stable; no state action occurred after the failure.
  - Script passes Ruff, pycompile, forbidden-action scan, SHA matching, and protected Gazebo isolation.
success_criteria:
  - Script accepts only q6-open, table-supported, in-target epoch-8 state and performs no gripper command.
  - MoveIt shadow detaches/syncs before retreat; 10 mm radial and 60 mm vertical pose plans execute.
  - Residual fingertip force stays at or below 0.05 N, cup displacement stays at or below 3 mm, and all fingertip contact clears within 0.05 s of radial execution.
  - Radial endpoint, vertical segment, final stable gate, Planning Scene readback, and unchanged final placement evaluator all pass.
failure_criteria: Any state mismatch, planning/execution failure, residual-force/displacement/grace violation, re-contact, support loss, target/stability/scene/provenance failure stops immediately.
invalid_criteria: Any reset, pause, q6 command, direct object state write, teleport, simulator attachment/constraint, model/config mutation, process restart, or unregistered retry invalidates diagnostic.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Qualified reset and fresh full lifecycle regardless of diagnostic result.
```

## Experiment EXP-132 Terminal Result

```yaml
experiment_id: EXP-132
status: VALID
terminal_result: PRE_MOTION_MOVEIT_START_STATE_COLLISION_REJECTED
terminal_time: 2026-08-12T06:02:18+08:00
command: python3 /tmp/so101_exp132_release_retreat.py
exit_code: 1
completed_phases:
  - preserved_released_state_validation
  - moveit_shadow_detach_and_exact_world_sync
failure:
  phase: radial_retreat_segment_1_planning
  error: RuntimeError retreat segment 1 planning failed: MOVEIT_PLAN_FAILED
  retreat_motion_started: false
  released_q6_rad: 0.7499563659574505
  released_cup_position_m: [-0.07801147859740672, -0.24742434117913314, 0.16551208060853104]
  released_cup_inside_target: true
  released_table_contact: true
  fixed_left_contact_count: 2
  moving_right_contact_count: 0
diagnosis:
  - Detaching the collision shadow correctly exposes the exact world cup before retreat.
  - The fixed gripper pad still lightly intersects or touches the synchronized world cup at the start state, so MoveIt rejects the radial plan before any physical motion.
  - The physical force/displacement/grace bounds cannot help a plan that is rejected by collision checking at its initial state.
  - The narrow corrective mechanism is a temporary Allowed Collision Matrix permission for only plastic_cup and the fixed gripper link during the 10 mm radial separation; the original ACM value must be restored and read back before the vertical segment.
evidence:
  diagnostic_json_sha256: 2c27599d089ab7b9554b8bca25175f080af3365875e255b7f0da57c3b725f0b4
  diagnostic_log_sha256: ba582dc53e0a6334cc5816e06cd46a6291a960b9ebc49daee50f627e8b07cf54
  diagnostic_script_sha256: 8e3e44c48fea0fe1dad0b51d77f8d34968cf4f61f07adde8d081368036cd2a57
decision: Do not count. Preserve epoch 8 and implement/test an exact, reversible ACM scope before another registered continuation diagnostic.
```

## Checkpoint CP-165

```yaml
checkpoint_id: CP-165
checkpoint_time: 2026-08-12T06:02:18+08:00
last_valid_experiment: EXP-132 VALID pre-motion planning failure
current_hypothesis: A reversible plastic_cup-to-gripper-only ACM scope permits planning from the intentional light fixed-pad contact while the existing physical force, displacement, and 50 ms clearing gates prevent contact exploitation.
working_tree_status: Intentional Task 13/14 changes. Protected Gazebo remains clean. Simulator remains epoch 8 running, q6 open, cup stable inside target; Planning Scene now contains the exact world cup and no attachment.
next_command: Add TDD-covered ACM mutation/readback helpers, rebuild, then preregister a no-release continuation diagnostic from the same epoch-8 state.
```

## Checkpoint CP-166

```yaml
checkpoint_id: CP-166
checkpoint_time: 2026-08-12T06:07:30+08:00
last_valid_experiment: EXP-132 VALID pre-motion planning failure
production_change:
  module: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/planning_scene_acm.py, 1a8c571fe9948a8d8203b0d87823787051da5c5436cceef0d940d865de226880]
  test: [src/so101_mujoco_demo_py/test/test_planning_scene_acm.py, 1671af42c6ce8d2c379c980a6efacc3a9042e686b08b45449c851f1aee0d84cd]
verification:
  tdd_red: collection failed because planning_scene_acm did not exist
  tdd_green: 11 focused tests passed
  ruff_package_gate: passed after mechanically fixing six I001 import-order findings inside only so101_mujoco_demo_py
  overlay_build: passed
  protected_gazebo_status: clean
scope_contract:
  - Only an explicit plastic_cup-to-gripper pair may be enabled.
  - The pair is symmetric; unrelated explicit and default ACM entries are preserved.
  - Missing or malformed readback fails closed.
  - The complete original ACM snapshot must be restored and read back before the vertical retreat segment.
next_command: Execute preregistered EXP-133 without reset, q6 command, or any pre-release motion.
```

## Experiment EXP-133

```yaml
experiment_id: EXP-133
prior_experiment: EXP-132 VALID pre-motion planning failure
status: RUNNING
lifecycle: PRESERVED_RELEASED_STATE_RADIAL_ONLY_REVERSIBLE_ACM_DIAGNOSTIC
run_mode: continue_from_stable_in_target_q6_open_epoch_8_state
hypothesis: A temporary plastic_cup-to-fixed-gripper ACM permission allows MoveIt to plan the 10 mm radial separation from the intentional light fixed-pad contact; physical force/displacement/grace gates clear that contact, and restoring the original ACM before the 60 mm vertical segment preserves normal collision checking.
single_variable: Add only the reversible plastic_cup-to-gripper ACM scope around radial separation. No jaw permission, q6 command, reset, pause, pre-release motion, target change, model change, or simulator constraint is allowed.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 8
  current_read_only_state:
    cup_position_m: [-0.07801145703404712, -0.24742434760930085, 0.16551228566006881]
    cup_inside_target: true
    table_contact: true
    moving_right_contact_count: 0
    fixed_left_contact_count: 2
    maximum_individual_fixed_left_force_n: 0.032816839062360034
  diagnostic_script: [/tmp/so101_exp133_release_retreat.py, ebcbe99508712c9bf43100ba5d0ca413f926064ae2c7044a5c574ba70e4cfa6f]
  acm_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/planning_scene_acm.py, 1a8c571fe9948a8d8203b0d87823787051da5c5436cceef0d940d865de226880]
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808]
preconditions:
  - Same epoch-8 released state is preserved and remains stable inside the target; no physical state action occurred after EXP-132.
  - Script passes Ruff, pycompile, forbidden-action provenance scan, SHA matching, and protected Gazebo isolation.
success_criteria:
  - Original plastic_cup-to-gripper ACM value is false; only that pair becomes true and plastic_cup-to-jaw remains false.
  - 10 mm radial plan and execution pass while fingertip force stays at or below 0.05 N, cup displacement stays at or below 3 mm, and all fingertip contact clears within 0.05 s.
  - Complete original ACM snapshot is restored and read back with the pair false before vertical planning.
  - 60 mm vertical plan executes with ordinary collision checking and zero fingertip contact; final placement and exact Planning Scene readback pass.
failure_criteria: Any state mismatch, ACM scope/readback/restoration failure, planning/execution failure, force/displacement/grace violation, re-contact, support loss, target/stability/scene/provenance failure stops immediately.
invalid_criteria: Any reset, pause, q6 command, direct object state write, teleport, simulator attachment/constraint, model/config mutation, process restart, jaw collision permission, global collision bypass, or unregistered retry invalidates diagnostic.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Qualified reset and fresh uninterrupted full lifecycle if the diagnostic passes; otherwise diagnose only its first failure.
```

## Experiment EXP-133 Terminal Result

```yaml
experiment_id: EXP-133
status: VALID
terminal_result: RELEASE_RETREAT_FINAL_PLACEMENT_PROVED
terminal_time: 2026-08-12T06:08:24+08:00
command: python3 /tmp/so101_exp133_release_retreat.py
exit_code: 0
completed_phases:
  - preserved_released_state_validation
  - exact_world_cup_scene_sync
  - radial_only_plastic_cup_to_gripper_acm_enable_and_readback
  - 10_mm_radial_pose_plan_and_execution
  - zero_fingertip_contact_stable_gate
  - complete_original_acm_restore_and_readback
  - 60_mm_vertical_pose_plan_and_execution_under_normal_collision_checking
  - final_physical_placement_and_scene_readback
results:
  radial_trajectory_points: 13
  vertical_trajectory_points: 32
  radial_acm_object: plastic_cup
  radial_acm_link: gripper
  moving_jaw_allowed: false
  acm_restored_before_vertical: true
  final_left_contact_count: 0
  final_right_contact_count: 0
  final_table_contact: true
  final_cup_position_m: [-0.0780114571055083, -0.2474243476370848, 0.16550312392426883]
  final_upright_tilt_rad: 0.017509988034019854
  final_sample_count: 18
  final_stable_duration_s: 0.204
  final_max_linear_speed_m_s: 0.0
  final_max_angular_speed_rad_s: 0.000007853601525831116
  planning_scene_world_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_attached_object_ids: []
provenance:
  physics_pause_calls: 0
  simulator_constraint_calls: 0
  direct_object_state_writes: 0
evidence:
  diagnostic_json_sha256: b4c8c17cc41c8d13fcfcf754a814bb04b6ed859b6e4b1769e7680a61bf728c52
  diagnostic_log_sha256: 37f80d294e8063b5885239c9c4d7f8c0a89d620832bd22d567e5f6c9e54283ad
  diagnostic_script_sha256: ebcbe99508712c9bf43100ba5d0ca413f926064ae2c7044a5c574ba70e4cfa6f
decision: Diagnostic hypothesis proved. Do not count as a full lifecycle because it resumed after release. Proceed to a qualified ResetWorld and one fresh uninterrupted lifecycle using the same frozen behavior.
```

## Checkpoint CP-167

```yaml
checkpoint_id: CP-167
checkpoint_time: 2026-08-12T06:08:24+08:00
last_valid_experiment: EXP-133 VALID release-retreat continuation success
current_hypothesis: The complete EXP-131 lifecycle plus the now-proven radial-only reversible ACM retreat will produce one valid uninterrupted physical pick-and-place after ResetWorld.
next_command: Preregister and execute EXP-134 ResetWorld qualification, including electronic postconditions and passive CUA visual verification, before preregistering the full lifecycle.
```

## Experiment EXP-134

```yaml
experiment_id: EXP-134
prior_experiment: EXP-133 VALID release-retreat continuation success
status: RUNNING
lifecycle: QUALIFIED_RESETWORLD_TO_TASK_START_BEFORE_FULL_LIFECYCLE
hypothesis: The patched ResetWorld transaction restores the exact task_start keyframe and MoveIt task scene from the epoch-8 final placement without process restart or model mutation.
single_variable: Execute one ResetWorld task_start transaction and exact Planning Scene restore. No task motion begins in this experiment.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  old_reset_epoch: 8
  keyframe: task_start
  expected_joint_positions_rad: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  expected_cup_position_m: [0.02, -0.28, 0.165]
  reset_script: [/tmp/so101_exp134_reset.py, 94f3307667e5f0a5b120724f6a170e1e5d52f0070a5f34884e4fb3dcac13578e]
  reset_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/reset.py, 4149260ad44e]
preconditions:
  - EXP-133 finished with zero fingertip contact, cup stable inside target, exact world cup, no attachment, and original ACM restored.
  - Reset script passes Ruff and pycompile; protected Gazebo status is clean.
success_criteria:
  - Service returns success; reset_epoch increments exactly 8 to 9 and authoritative paused step-zero evidence belongs to the same session.
  - All six joints and the cup return within configured task_start tolerances; arm and gripper controllers are active.
  - Planning Scene readback is exactly table 1, pedestal 1, plastic_cup 13, with no attached cup.
  - Passive CUA shows RViz left and MuJoCo Viewer right with the arm, pedestal, table, cup, and red target ring visibly restored to task_start; Viewer is Running or visibly in the qualified paused reset state as recorded.
failure_criteria: Any epoch/session/joint/object/controller/scene/evidence/visual mismatch fails and is retained.
invalid_criteria: Process restart, direct object state write outside ResetWorld, model/config mutation, task motion before terminal evidence, or missing CUA evidence invalidates the experiment.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Only after electronic and visual reset acceptance, preregister and execute the fresh full lifecycle at epoch 9.
```

## Experiment EXP-134 Terminal Result

```yaml
experiment_id: EXP-134
status: VALID
terminal_result: QUALIFIED_RESET_AND_SCENE_RESTORE_PROVED
terminal_time: 2026-08-12T06:11:45+08:00
command: python3 /tmp/so101_exp134_reset.py
exit_code: 0
electronic_results:
  reset_epoch: [8, 9]
  simulation_step: 0
  paused: true
  cup_position_m: [0.02, -0.28, 0.165]
  cup_orientation_xyzw: [0.0, 0.0, 0.0, 1.0]
  cup_linear_velocity_m_s: [0.0, 0.0, 0.0]
  cup_angular_velocity_rad_s: [0.0, 0.0, 0.0]
  joint_positions_rad: [0.00000005171177762341105, 0.0002673190157197849, 0.00023641112083134245, 0.000025309125207896054, 0.000000005750872309928381, -0.000000156048348687488]
  controllers_active: true
  planning_scene_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  planning_scene_attached_object_ids: []
visual_results:
  method: passive CUA via codex-cua
  rviz_left: true
  mujoco_viewer_right: true
  task_start_horizontal_arm: true
  open_gripper_clear_of_upright_cup: true
  complete_scene_and_red_ring_visible: true
  viewer_pause_visible: true
evidence:
  reset_json_sha256: fa7164469debbc37fdab6db2fc9c6a2978d7833c1df7937eb864bd332a8dc725
  reset_log_sha256: 0c660ba75dbe0d156da32c6bbcfb444f7edd344266f4b701837ca41d255301b3
  cua_screenshot_sha256: 9d4f000590ab8d93f348b384e0464044344869c85c9fb6b57bf87f686cf19341
decision: ResetWorld is electronically and visually accepted. Epoch 9 is frozen at task_start for EXP-135.
```

## Experiment EXP-135

```yaml
experiment_id: EXP-135
prior_experiment: EXP-134 VALID qualified reset
status: RUNNING
lifecycle: UNINTERRUPTED_PHYSICAL_PICK_TRANSPORT_PLACE_RELEASE_RETREAT_FINAL_PROOF
hypothesis: The frozen staged physical grasp/transport/alignment behavior plus the proven radial-only reversible ACM retreat completes one uninterrupted pick-and-place from epoch-9 task_start with the cup stable inside the unchanged target.
single_variable: Integrate the EXP-133-proven ACM scope into the otherwise unchanged EXP-131 full lifecycle. No target, model, friction, controller, grasp, alignment, or motion waypoint changes.
frozen_inputs:
  simulation_session_id: so101-task14-acceptance
  reset_epoch: 9
  start_keyframe: task_start
  phase_order:
    - resume_physics_once
    - staged_approach_15_waypoints_to_close_ready
    - bounded_bilateral_contact_hold
    - physical_micro_lift
    - policy_lift_waypoint_1
    - remaining_lift_waypoints_2_to_5
    - transport_5_waypoints
    - descend_3_waypoints
    - bounded_place_alignment
    - physical_q6_release
    - radial_only_reversible_acm_retreat_10_mm
    - original_acm_restore_and_readback
    - ordinary_collision_checked_vertical_retreat_60_mm
    - final_physical_and_scene_proof
  suite_manifest_sha256: 61cce69310a5abfe5eb0ed83247269802f19f75c47c67c67e42d612e6dda8b73
  runner: [/tmp/so101_exp135_run.bash, 1fa0396a6e3fbac33d8b383d23cf1c35e0b71aa2d80387c88dd699441c6fa755]
  release_retreat_script: [/tmp/so101_exp135_release_retreat.py, b93fbe3f7c1afc4de996e7a823eb988c4d81608413d6f431b9cc918e1a33056b]
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808]
  acm_source: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/planning_scene_acm.py, 1a8c571fe9948a8d8203b0d87823787051da5c5436cceef0d940d865de226880]
preconditions:
  - EXP-134 electronically and visually proved epoch-9 task_start; simulation remains paused and no subsequent state action occurred.
  - All eight phase scripts pass pycompile and Ruff; runner passes Bash syntax; forbidden simulator-constraint/object-write scan passes.
  - Package Ruff gate and focused tests/build pass; protected Gazebo status and diff are clean.
success_criteria:
  - Every phase completes in order without reset, pause after the single resume, process restart, direct object state write, simulator attachment, teleport, or unbounded retry.
  - Bilateral physical grasp remains force/contact/support-safe through lift, transport, descend, and bounded alignment.
  - q6 opens; released cup remains table-supported within force/displacement bounds; radial contact clears within 0.05 s.
  - Only plastic_cup-to-gripper is temporarily ACM-allowed; plastic_cup-to-jaw remains false; complete original ACM is restored before vertical planning.
  - Final cup is upright and stable inside x [-0.085,-0.075], y [-0.255,-0.245], supported by table, with zero fingertip contact; Planning Scene has exact world cup and no attachment.
  - Passive final CUA shows RViz left, Viewer right, cup visibly inside the red ring, arm/gripper clear above it, complete scene, and Viewer Running.
failure_criteria: Any phase, planning, execution, convergence, contact, force, support, alignment, placement, ACM, scene, provenance, or visual gate failure stops immediately and is retained.
invalid_criteria: Any reset/pause after resume, direct object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, global/jaw ACM bypass, model/config mutation, process restart, missing evidence, or unregistered retry invalidates the run.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: On success, capture passive CUA, then promote the proven lifecycle into the production runner; on failure, preserve and diagnose only the first failure.
```

## Experiment EXP-135 Terminal Result

```yaml
experiment_id: EXP-135
status: VALID
terminal_result: UNINTERRUPTED_PHYSICAL_PICK_AND_PLACE_VISUALLY_PROVED
terminal_time: 2026-08-12T06:16:45+08:00
command: /tmp/so101_exp135_run.bash
exit_code: 0
completed_phases:
  - resume_physics_once
  - staged_approach_15_waypoints
  - bounded_bilateral_contact_hold
  - physical_micro_lift
  - policy_lift_5_waypoints_total
  - transport_5_waypoints
  - descend_3_waypoints
  - bounded_place_alignment_1_attempt
  - physical_q6_release
  - radial_only_reversible_acm_retreat_10_mm
  - original_acm_restore_and_readback
  - ordinary_collision_checked_vertical_retreat_60_mm
  - final_physical_and_scene_proof
phase_results:
  staged_approach_status: CLOSE_READY
  staged_approach_segments: 15
  contact_hold_status: CONTACT_ONLY_PROVED
  contact_hold_samples: 73
  micro_lift_status: PHYSICAL_MICRO_LIFT_PROVED
  remaining_lift_status: REMAINING_FORMAL_LIFT_PROVED
  remaining_lift_segments: 4
  transport_status: FORMAL_MOVE_ABOVE_PLACE_PROVED
  transport_segments: 5
  descend_status: FORMAL_DESCEND_TO_PRE_RELEASE_CLEARANCE_PROVED
  descend_segments: 3
  place_alignment_status: PRE_RELEASE_ALIGNMENT_PROVED
  release_retreat_status: RELEASE_RETREAT_FINAL_PLACEMENT_PROVED
final_physical_result:
  reset_epoch: 9
  cup_position_m: [-0.07866599849254928, -0.2473756541793162, 0.1653858428271493]
  upright_tilt_rad: 0.017638161717676775
  table_contact: true
  left_fingertip_contact_count: 0
  right_fingertip_contact_count: 0
  maximum_linear_speed_m_s: 0.0
  maximum_angular_speed_rad_s: 0.000010239843591340283
  stable_sample_count: 18
  stable_duration_s: 0.204
  target_bounds_xy_m: {x: [-0.085, -0.075], y: [-0.255, -0.245]}
planning_scene_result:
  world_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  attached_object_ids: []
radial_acm_result:
  allowed_pair: [plastic_cup, gripper]
  moving_jaw_allowed: false
  restored_before_vertical: true
  restored_pair_allowed: false
visual_result:
  method: passive CUA via codex-cua
  rviz_left: true
  mujoco_viewer_right: true
  upright_cup_visibly_inside_red_ring: true
  opened_gripper_and_arm_clear: true
  complete_scene_visible: true
  viewer_status_running: true
provenance:
  lifecycle_reset_calls_after_resume: 0
  lifecycle_pause_calls_after_resume: 0
  direct_object_state_writes: 0
  simulator_constraint_calls: 0
  process_restarts: 0
evidence:
  master_log_sha256: d6503a12b4fd0c1c6368119f7e232374cf530beb5f576a08844d11a57c012075
  staged_approach_json_sha256: 18dfe1078134e61a96fe56ca77da05265b658fe462d28d2a7f7b0d23adaca7fa
  contact_hold_json_sha256: 1a6c048da234a35fa1c47734e4713ecea45ccb97c0b1271b73505b4d076b5772
  micro_lift_json_sha256: 70b1a5783d0a99bef8285bd4bb2c26ba40539a5d1afec92a12d5723dd51693a1
  transport_json_sha256: 1a38a19195dd49cd1d91eb925739f01db225036c7ebb0fb46e2a89762b177b67
  place_alignment_json_sha256: 6154f8741cc295c28e403c1fffd88cf6d5f8a36999a99d87970dd0f8eaf5117f
  release_retreat_json_sha256: fccf4239950d2872568a5f4135d7c1a05959c42d5363a5c31ea5e3db18b42c39
  release_retreat_log_sha256: 04fb4c8aa3a9275e2709260a67c72e2355babad5a588db4dd828c664e999cfc7
  cua_screenshot_sha256: 829e9546104144a9a8e8cacce43311f67a9bd0ec2f39e24ca4e43b7db321b7c8
decision: Count as the required one successful uninterrupted physical pick-and-place. Next, promote this exact behavior into the production runner and pass package gates before the planned rebase and Teleop integration.
```

## Checkpoint CP-168

```yaml
checkpoint_id: CP-168
checkpoint_time: 2026-08-12T06:16:45+08:00
last_valid_experiment: EXP-135 VALID uninterrupted physical pick-and-place success
accepted_success_count: 1
current_state: Viewer remains Running at epoch 9 with the cup stable inside the target, arm/gripper clear, exact world cup in Planning Scene, no attachment, and original ACM restored.
next_command: Implement the proven phase lifecycle as the so101_mujoco_demo_py production execution path, run full quality/provenance/isolation gates, commit and push, then create the continuation branch and rebase it on latest main for Teleop integration.
```

## Experiment EXP-136 Registration

```yaml
experiment_id: EXP-136
registered_at: 2026-08-12T06:35:51+08:00
purpose: Qualify ResetWorld immediately before validating the promoted production execution entrypoint.
simulation_session_id: so101-task14-acceptance
expected_epoch_transition: 9 -> 10
initial_state: EXP-135 terminal state; cup stable inside the target and simulation running.
state_action: Exactly one ResetWorld(task_start), followed by Planning Scene restore and passive CUA inspection.
reset_script: [/tmp/so101_exp136_reset.py, 7c0f50f6df10749e39968dba2e630eb78a2d91b00559ffacdf62582446eee210]
success_criteria:
  - Reset receipt and authoritative evidence both prove epoch 10 and paused step-zero task_start.
  - Arm is at the six-joint task_start state, controllers are active, and cup is upright at [0.02, -0.28, 0.165] within 3 mm.
  - Planning Scene contains exact table, pedestal, and 13-primitive cup with no attached cup.
  - Passive CUA visibly proves RViz left, MuJoCo Viewer right, task_start arm, open gripper, original cup position, complete scene, and Paused status.
failure_criteria: Any reset, epoch, pose, controller, scene, or visual mismatch is retained and blocks production validation.
invalid_criteria: Any additional reset, object state write, teleport, simulator attachment, hidden constraint, model mutation, or GUI manipulation invalidates the experiment.
evidence_root: /tmp/so101-task14-acceptance
decision: PENDING.
next_experiment: Only after valid reset and visual proof, pre-register and execute the production runner as EXP-137.
```

## Experiment EXP-136 Terminal Result

```yaml
experiment_id: EXP-136
status: VALID
terminal_result: RESET_WORLD_AND_VISUAL_TASK_START_PROVED
terminal_time: 2026-08-12T06:38:02+08:00
reset_result:
  reset_epoch: 9 -> 10
  simulation_step: 0
  paused: true
  cup_position_world_m: [0.02, -0.28, 0.165]
  cup_orientation_world_xyzw: [0.0, 0.0, 0.0, 1.0]
  cup_linear_velocity_world_m_s: [0.0, 0.0, 0.0]
  controllers_active: true
planning_scene_result:
  world_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  attached_object_ids: []
visual_result:
  method: passive CUA via codex-cua
  rviz_left: true
  mujoco_viewer_right: true
  task_start_arm_and_open_gripper: true
  upright_cup_at_original_position: true
  complete_scene_visible: true
  viewer_status_paused: true
evidence:
  reset_json_sha256: 55fff4795fa0495cef8bfd77c2842f4e186bf7d5f7baa717511a147bf4b95879
  reset_log_sha256: c9030b8fb1d6a8eabca953ab7309bef7b84324f1518bf038608b11bfe9978eb5
  cua_screenshot_sha256: 642a21981f7e54e195fa58838eb6f208a29301570b660e7cafc01f77f688e52a
decision: Proceed once to the production runner validation at epoch 10.
```

## Experiment EXP-137 Registration

```yaml
experiment_id: EXP-137
registered_at: 2026-08-12T06:38:02+08:00
purpose: Validate that the promoted pick_place_state_machine production execution entrypoint reproduces the proven uninterrupted physical lifecycle.
simulation_session_id: so101-task14-acceptance
expected_reset_epoch: 10
initial_state: EXP-136 valid paused task_start with exact Planning Scene.
command: pick_place_state_machine --mode execute --execute --session-id so101-task14-acceptance --expected-reset-epoch 10 --evidence-root /tmp/so101-task14-acceptance/exp137-live-runtime --motion-policy src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml
production_sources:
  live_runtime: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_runtime.py, e2f6af57391fcc22925433ce851a31812527ff08dd2b2cbcddf0151f00c38ac0]
  cli: [src/so101_mujoco_demo_py/so101_mujoco_demo_py/cli.py, bfa38273761ebef7ce4b4023c617bebb858f790aff9a8f4e7f61cfa5e882f7fa]
  policy: [src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml, d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808]
preconditions:
  - EXP-136 qualified epoch-10 paused task_start and passive visual state.
  - Fresh two-package colcon build and test passed: 359 tests, 0 errors, 0 failures, 4 skipped.
  - Package pytest passed 344 tests with 4 skipped; Ruff and migration isolation gates passed.
success_criteria:
  - Production entrypoint resumes physics exactly once and completes all nine registered phases without reset, pause, process restart, direct object state write, simulator attachment, teleport, or hidden constraint.
  - Manifest is DONE, every phase exit code is zero, every evidence artifact has a SHA-256 digest, and all evidence is session/epoch exact.
  - Final cup is upright and stable inside the target bounds, table-supported, with zero fingertip contact; original ACM is restored and exact Planning Scene has no attachment.
  - Passive final CUA proves RViz left, Viewer right, cup visibly inside red ring, arm/gripper clear, complete scene, and Viewer Running.
failure_criteria: Any phase, evidence, physical, scene, ACM, provenance, or visual failure stops and is retained.
invalid_criteria: Any reset/pause after resume, direct object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, model mutation, unregistered retry, or GUI manipulation invalidates the run.
evidence_root: /tmp/so101-task14-acceptance/exp137-live-runtime
decision: PENDING.
next_experiment: None without a new ledger registration; on success perform clean shutdown, commit/push, then rebase continuation branch for Teleop integration.
```

## Experiment EXP-137 Terminal Result

```yaml
experiment_id: EXP-137
status: FAILED_BEFORE_STATE_ACTION
terminal_time: 2026-08-12T06:39:13+08:00
failure: ROS overlay setup was sourced directly by the inherited zsh with stale COLCON_CURRENT_PREFIX; /opt/ros/jazzy/setup.bash attempted to load setup.sh from the worktree root.
state_actions_performed: 0
physics_resumed: false
runner_started: false
evidence_root_created: false
retention: The tmux pane output is retained; there was no runtime master log because the shell's && chain stopped before the tee pipeline.
decision: Do not count. Preserve epoch-10 paused task_start and pre-register a new execution using an isolated Bash wrapper that clears COLCON_CURRENT_PREFIX.
```

## Experiment EXP-138 Registration

```yaml
experiment_id: EXP-138
registered_at: 2026-08-12T06:39:13+08:00
purpose: Execute the same production-runner validation from a deterministic Bash environment after EXP-137 failed before any state action.
simulation_session_id: so101-task14-acceptance
expected_reset_epoch: 10
initial_state: Unchanged EXP-136 valid paused task_start; EXP-137 performed zero state actions.
command: /tmp/so101_exp138_run.bash
runner_wrapper: [/tmp/so101_exp138_run.bash, bc8e97d491f22eb4dba8382de0ab7d773a029b3650792149fc8f9748c1357ed4]
environment_fix: Clear inherited COLCON_CURRENT_PREFIX, then source ROS, qualified fork, active integration overlay, and fresh production overlay under Bash.
success_criteria:
  - Production entrypoint resumes physics exactly once and completes all nine registered phases without reset, pause, process restart, direct object state write, simulator attachment, teleport, or hidden constraint.
  - Manifest is DONE, every phase exit code is zero, every evidence artifact has a SHA-256 digest, and all evidence is session/epoch exact.
  - Final cup is upright and stable inside target bounds, table-supported, with zero fingertip contact; original ACM restored and exact Planning Scene has no attachment.
  - Passive final CUA proves RViz left, Viewer right, cup inside red ring, arm/gripper clear, complete scene, and Viewer Running.
failure_criteria: Any environment, phase, evidence, physical, scene, ACM, provenance, or visual failure stops and is retained.
invalid_criteria: Any reset/pause after resume, direct object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, model mutation, unregistered retry, or GUI manipulation invalidates the run.
evidence_root: /tmp/so101-task14-acceptance/exp138-live-runtime
decision: PENDING.
next_experiment: None without a new ledger registration.
```

## Experiment EXP-138 Terminal Result

```yaml
experiment_id: EXP-138
status: FAILED_BEFORE_STATE_ACTION
terminal_time: 2026-08-12T06:40:37+08:00
exit_code: 127
failure: The ament_python console script is intentionally installed under lib/so101_mujoco_demo_py and is not a bare PATH command.
state_actions_performed: 0
physics_resumed: false
runner_started: false
evidence_root_created: false
evidence:
  master_log_sha256: 64bde3c94926d5ff5adb233fe2af1f5fb8b6a8520c3a9954713f2d4b815a97e0
diagnostic_readback: ros2 pkg executables so101_mujoco_demo_py lists pick_place_state_machine.
decision: Do not count. Preserve epoch-10 paused task_start and invoke the installed formal entrypoint through ros2 run in a new registered experiment.
```

## Experiment EXP-139 Registration

```yaml
experiment_id: EXP-139
registered_at: 2026-08-12T06:40:37+08:00
purpose: Execute the installed production runner through the canonical ROS 2 console-script entrypoint.
simulation_session_id: so101-task14-acceptance
expected_reset_epoch: 10
initial_state: Unchanged EXP-136 valid paused task_start; EXP-137 and EXP-138 performed zero state actions.
command: /tmp/so101_exp139_run.bash
runner_wrapper: [/tmp/so101_exp139_run.bash, 48a2bd6f6bd195aece0c6707962295fbb219669721d0bafc6b952c87df71c9a0]
formal_entrypoint: ros2 run so101_mujoco_demo_py pick_place_state_machine --mode execute --execute
success_criteria:
  - Production entrypoint resumes physics exactly once and completes all nine registered phases without reset, pause, process restart, direct object state write, simulator attachment, teleport, or hidden constraint.
  - Manifest is DONE, every phase exit code is zero, every evidence artifact has a SHA-256 digest, and all evidence is session/epoch exact.
  - Final cup is upright and stable inside target bounds, table-supported, with zero fingertip contact; original ACM restored and exact Planning Scene has no attachment.
  - Passive final CUA proves RViz left, Viewer right, cup inside red ring, arm/gripper clear, complete scene, and Viewer Running.
failure_criteria: Any environment, phase, evidence, physical, scene, ACM, provenance, or visual failure stops and is retained.
invalid_criteria: Any reset/pause after resume, direct object qpos/qvel write, teleport, weld/equality/adhesion/mocap constraint, hidden physical attachment, model mutation, unregistered retry, or GUI manipulation invalidates the run.
evidence_root: /tmp/so101-task14-acceptance/exp139-live-runtime
decision: PENDING.
next_experiment: None without a new ledger registration.
```

## Experiment EXP-139 Terminal Result

```yaml
experiment_id: EXP-139
status: VALID
terminal_result: INSTALLED_PRODUCTION_RUNNER_PHYSICAL_PICK_AND_PLACE_VISUALLY_PROVED
terminal_time: 2026-08-12T06:44:33+08:00
exit_code: 0
completed_phases:
  - staged_approach
  - contact_hold
  - micro_lift
  - policy_lift_waypoint1
  - remaining_lift
  - transport
  - descend
  - place_alignment
  - release_retreat
manifest_result:
  status: DONE
  expected_reset_epoch: 10
  phase_exit_codes_all_zero: true
  artifact_sha256_count: 9
final_physical_result:
  cup_position_world_m: [-0.07935794584628292, -0.24539781774692443, 0.16514775924087624]
  upright_tilt_rad: 0.012631139187870259
  table_contact: true
  left_fingertip_contact_count: 0
  right_fingertip_contact_count: 0
  maximum_linear_speed_m_s: 0.0
  maximum_angular_speed_rad_s: 0.0
  stable_sample_count: 21
  stable_duration_s: 0.2
planning_scene_result:
  world_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  attached_object_ids: []
radial_acm_result:
  allowed_pair: [plastic_cup, gripper]
  moving_jaw_allowed: false
  restored_before_vertical: true
  restored_pair_allowed: false
visual_result:
  method: passive CUA via codex-cua
  rviz_left: true
  mujoco_viewer_right: true
  upright_cup_visibly_inside_red_ring: true
  opened_gripper_and_arm_clear: true
  complete_scene_visible: true
  viewer_status_running: true
provenance:
  lifecycle_reset_calls_after_resume: 0
  lifecycle_pause_calls_after_resume: 0
  direct_object_state_writes: 0
  simulator_constraint_calls: 0
  process_restarts: 0
evidence:
  master_log_sha256: 76acc587ccbb332fbb09940fe0d6495b2d9c8bb73bdce6ef2d34d60174bbbdb4
  manifest_sha256: 50db4a99d6766233dc62ac709d84be5657e348e1bfe8a2511f5ffa2cc0b6b305
  release_retreat_json_sha256: 93c9ae940c133997e10b14318fd733ded491b883df76b2160da21995e488f32d
  cua_screenshot_sha256: 2d9b1d4677c31fa57f17eb27b84f3560c280d7d0e3abea6308e211b4679eb8e6
decision: Production execution entrypoint is live-qualified. Proceed to clean shutdown, pre-rebase commit/push, and the registered Teleop continuation work.
```

## Checkpoint CP-169

```yaml
checkpoint_id: CP-169
checkpoint_time: 2026-08-12T06:44:33+08:00
last_valid_experiment: EXP-139 VALID installed production-runner physical pick-and-place
accepted_success_count: 2
current_state: Viewer remains Running at epoch 10 with the cup stable inside target, arm/gripper clear, exact Planning Scene, no attachment, and original ACM restored.
next_command: Perform scoped clean shutdown and verify owned processes exit cleanly; then commit and push codex/so101-mujoco-ros2 before creating the non-force continuation branch for rebase and Teleop integration.
```

## Experiment EXP-140 Registration

```yaml
experiment_id: EXP-140
registered_at: 2026-08-12T06:49:25+08:00
purpose: Reproduce and verify the fork-side clean GUI shutdown fix after the accepted production pick-place.
baseline_failure:
  mujoco_ros2_control_exit_code: -11
  stack: libGLdispatch during controller-manager shutdown
  observation: Simulate and its GLFW/OpenGL context were created on the render thread but the Simulate member was destroyed later on the controller-manager main thread.
hypothesis: Stop physics first, then signal the render thread to destroy Simulate on the context-owning thread before joining it.
patched_sources:
  header_sha256: f2f86c124d11510bb498b78c51e9eb335cf7e87593a01909356e9823727457e0
  source_sha256: 377efae3ec07587bd6feed6eaf563b76456d90d0f5f06c7becbb64fe74ab09ad
build_artifact:
  libmujoco_ros2_control_so_sha256: 6599ee0d4c36f603ea2d4a7aed573f526645f6dfd94cf6f4fd7cdf1b633e9ee7
test_precondition:
  - Static owner-thread destruction contract failed before the patch and passes after it.
  - Fork core build passed and all four core test targets passed, including 10 headless tests and 96 URDF conversion tests.
state_action: Launch one isolated GUI MuJoCo stack on ROS_DOMAIN_ID 150 from the patched fork overlay, wait for readiness, then send one scoped Ctrl-C to its tmux pane.
success_criteria:
  - Viewer and controller stack reach readiness using the patched library.
  - On Ctrl-C, controllers deactivate, physics stops, render thread releases graphics resources, and ros2_control_node exits code 0 with no SIGSEGV/libGLdispatch stack.
  - No unrelated process or tmux session is signaled.
failure_criteria: Any launch, readiness, hang, forced kill, SIGSEGV, nonzero child exit, or graphics teardown error is retained.
invalid_criteria: Reusing the old fork overlay, signaling a broad process set, or editing the model during the run invalidates the test.
evidence_root: /tmp/so101-shutdown-exp140
decision: PENDING.
next_experiment: Diagnose only if the owner-thread teardown still fails; otherwise update the fork release and dependency lock.
```

## Experiment EXP-140 Terminal Result

```yaml
experiment_id: EXP-140
status: INCONCLUSIVE_TEST_HARNESS_FAILURE
terminal_time: 2026-08-12T06:51:25+08:00
launch_ready: true
observed_exit: 120
segmentation_fault_observed: false
failure: The tee pipeline shared the foreground terminal process group; Ctrl-C terminated the log transport before complete launch shutdown output could be retained, so controller deactivation and child exit status were not provable.
evidence:
  partial_launch_log_sha256: 93f8a5dc8ecd95fd82b16511abdd33b5dd3a9afa260bf060efda34b1b2239a94
decision: Do not accept. Re-run with ros2 launch exec'd directly and simple file redirection, retaining tmux pane_dead_status as the authoritative process exit.
```

## Experiment EXP-141 Registration

```yaml
experiment_id: EXP-141
registered_at: 2026-08-12T06:51:25+08:00
purpose: Repeat the fork GUI shutdown test with a signal-transparent launch harness.
state_action: Start the patched GUI stack on ROS_DOMAIN_ID 151; after all three controllers activate, send one Ctrl-C to the single owned tmux pane.
runner: [/tmp/so101_exp141_shutdown.bash, b9ca90a696b634e519dd309997ec356199d11851321da3e2043c036e0feb877d]
harness: exec ros2 launch with direct stdout/stderr file redirection; tmux remain-on-exit records the real pane exit code.
success_criteria:
  - arm_controller, gripper_controller, and joint_state_broadcaster all activate before shutdown.
  - Shutdown log shows controller deactivation, hardware deactivate/shutdown, and clean ros2_control_node and robot_state_publisher exits.
  - tmux pane exit is zero or the launcher's documented Ctrl-C success status, with no -11, SIGSEGV, libGLdispatch error, hang, or forced kill.
failure_criteria: Missing readiness, missing shutdown lifecycle, graphics crash, non-clean child exit, hang, or forced kill.
invalid_criteria: Old fork overlay, broad process signal, model mutation, or tee/pipeline in the signal path.
evidence_root: /tmp/so101-shutdown-exp141
decision: PENDING.
next_experiment: None without new registration.
```

## Experiment EXP-141 Terminal Result

```yaml
experiment_id: EXP-141
status: INVALID_RUNTIME_PROVENANCE
terminal_time: 2026-08-12T06:53:12+08:00
launch_ready: true
shutdown_lifecycle_observed: true
observed_child_exit: -11
invalid_reason: The launch log proves ros2_control_node was resolved from /tmp/so101-fork-reset-test/install, because sourcing the project overlay reintroduced its build-time fork underlay after the patched fork prefix.
evidence:
  launch_log_sha256: 7a3b6b9b32a16f10e0e18e3a54fc684d92af4b7c629150c039ac4197a9d4259c
decision: Do not evaluate the patch from this run. Reorder overlays and record ros2 pkg prefix before launch.
```

## Experiment EXP-142 Registration

```yaml
experiment_id: EXP-142
registered_at: 2026-08-12T06:53:12+08:00
purpose: Validly test patched fork shutdown with explicit runtime-prefix proof.
runner: [/tmp/so101_exp142_shutdown.bash, b9036dc64c6a264c14ceb63b619d0adbb0d207587717a1f6cae30c756c5d8e1b]
state_action: Launch GUI stack on ROS_DOMAIN_ID 152 after sourcing the project overlay first and the patched fork overlay last; after all controllers activate, send one Ctrl-C to the owned tmux pane.
runtime_provenance_gate:
  required_mujoco_prefix: /tmp/so101-fork-shutdown-build/install/mujoco_ros2_control
  required_project_prefix: /tmp/so101-production-build-v2/install/so101_mujoco_demo_py
  evidence_file: /tmp/so101-shutdown-exp142/runtime-prefixes.txt
success_criteria:
  - Runtime-prefix evidence exactly names the patched fork and fresh project overlay.
  - All three controllers activate before shutdown.
  - Shutdown log shows controller and hardware teardown, and clean ros2_control_node/robot_state_publisher exits.
  - tmux pane exit is zero, with no -11, SIGSEGV, libGLdispatch error, hang, or forced kill.
failure_criteria: Any provenance mismatch, readiness gap, missing teardown lifecycle, crash, nonzero exit, hang, or forced kill.
invalid_criteria: Old fork prefix, broad process signal, model mutation, or pipeline in the signal path.
evidence_root: /tmp/so101-shutdown-exp142
decision: PENDING.
next_experiment: None without new registration.
```

## Experiment EXP-142 Terminal Result

```yaml
experiment_id: EXP-142
status: VALID
terminal_result: PATCHED_MUJOCO_GUI_CLEAN_SHUTDOWN_PROVED
terminal_time: 2026-08-12T06:58:46+08:00
runtime_provenance:
  mujoco_ros2_control_prefix: /tmp/so101-fork-shutdown-build/install/mujoco_ros2_control
  so101_mujoco_demo_py_prefix: /tmp/so101-production-build-v2/install/so101_mujoco_demo_py
readiness:
  arm_controller_active: true
  gripper_controller_active: true
  joint_state_broadcaster_active: true
shutdown:
  controller_deactivation_observed: true
  hardware_deactivate_and_shutdown_observed: true
  robot_state_publisher_clean_exit: true
  ros2_control_node_clean_exit: true
  tmux_pane_exit_code: 0
  segmentation_fault: false
  libGLdispatch_error: false
evidence:
  launch_log_sha256: 8b2cc18e1c5436abac1e041926e60ad62fdbc16fcce4d269b1782f0cb92efe19
  runtime_prefixes_sha256: f97ee30a822d08f2ceeb039f39d72afd1b1934377dc6fc0336b1e6b1c641f4c1
decision: Accept the fork-side context-owner teardown fix. Validate the MoveIt ordered shutdown executable in the formal project composition next.
```

## Experiment EXP-143 Registration

```yaml
experiment_id: EXP-143
registered_at: 2026-08-12T06:58:46+08:00
purpose: Validate a project-owned MoveIt entrypoint that keeps the ROS context valid until MoveGroupExe, MoveItCpp, and the planning scene monitor are destroyed.
baseline_failure:
  executable: /opt/ros/jazzy/lib/moveit_ros_move_group/move_group
  exit_code: -11
  stack: MoveItCpp -> TrajectoryExecutionManager -> rclcpp::Node -> CallbackGroup destructor after SIGINT context shutdown
implementation:
  source: src/so101_mujoco_support/src/so101_move_group.cpp
  source_sha256: 15931e3d1b31ba104b8cda6a8ba9ae5581200da8e305276d69a6c6f7c2ccfb20
  executable_sha256: 5ab239f1962cf9ee8ad247b5c59c34abd7eca4e75b4628333f1b8e07b3e0f809
  upstream_basis: moveit/moveit2 tag 2.12.4 move_group.cpp
  change: Disable the default rclcpp signal handler, poll a signal-safe shutdown flag, remove the node from the executor, destroy all MoveIt objects, then call rclcpp::shutdown.
runner: [/tmp/so101_exp143_ordered_shutdown.bash, acb47851f6b7b854c5f3dbf825302ebd8ae519589772fd9b41e3b801545471cc]
state_action: Run the formal so101_pick_place.launch.py in GUI dry-run mode on ROS_DOMAIN_ID 153 and let its workflow-owned Shutdown event terminate the complete stack.
success_criteria:
  - Runtime provenance selects patched MuJoCo, fresh support/demo overlay, and installed so101_move_group.
  - Planning Scene setup succeeds and dry-run workflow reaches DONE.
  - Workflow-owned shutdown cleanly exits so101_move_group, ros2_control_node, and robot_state_publisher with no -11, SIGSEGV, graphics teardown error, hang, or forced kill.
  - tmux pane exit code is zero and evidence/log files are retained.
failure_criteria: Any provenance, launch, scene, workflow, process-exit, teardown, or timeout failure.
invalid_criteria: Using the apt move_group executable, old fork overlay, broad process signal, or model mutation.
evidence_root: /tmp/so101-shutdown-exp143
decision: PENDING.
next_experiment: None without new registration.
```

## Experiment EXP-143 Terminal Result

```yaml
experiment_id: EXP-143
status: FAILED
terminal_time: 2026-08-12T07:00:23+08:00
runtime_provenance_valid: true
planning_scene_setup: succeeded
dry_run_workflow: succeeded
workflow_owned_shutdown: triggered
mujoco_ros2_control_clean_exit: true
robot_state_publisher_clean_exit: true
so101_move_group_exit_code: -11
last_moveit_log: Deleting MoveItCpp
finding: Keeping the ROS context valid until MoveIt object teardown was necessary but not sufficient; an internal MoveIt lifetime/thread race remains.
evidence:
  launch_log_sha256: dc6035a17a92864d54912224074d1ac863e25dacd04181213049e76549c3eb99
  workflow_json_sha256: 9ba42b336e98a68004f1a90cd53ade1f69f03c2ce035c9e4796caf7cf2617c9a
  runtime_prefixes_sha256: c5f267ec6de007921a611493a74e5f1159c011413c0638cdab250075afe05b43
decision: Retain failure and obtain an all-thread GDB backtrace from the same lifecycle before changing teardown again.
```

## Experiment EXP-144 Registration

```yaml
experiment_id: EXP-144
registered_at: 2026-08-12T07:00:23+08:00
purpose: Capture the exact crashing thread and frames for the ordered MoveIt shutdown failure.
state_action: Re-run the same formal GUI dry-run lifecycle on ROS_DOMAIN_ID 154 with only so101_move_group under noninteractive GDB.
debug_launch: [/tmp/so101_exp144_gdb.launch.py, 0929b01c83afe8100a4983e8298784d7a4983502b23cb18beb012ea5c308a984]
runner: [/tmp/so101_exp144_gdb_shutdown.bash, 6f9ce95960e0a351ba9e4ceb50c0a8722ddaabb6ed8145ab25189135b4658573]
gdb_commands: run; thread apply all bt
success_criteria:
  - Same planning and workflow lifecycle completes.
  - If a crash occurs, launch.log contains the faulting signal, thread, and all-thread backtrace sufficient to identify the owning MoveIt component.
  - Other stack processes shut down without broad signaling or forced kill.
failure_criteria: Debugger fails to start, lifecycle differs before shutdown, backtrace is missing, or stack hangs.
invalid_criteria: Source/model mutation during the run, apt move_group substitution, old fork overlay, or unregistered retry.
evidence_root: /tmp/so101-shutdown-exp144
decision: PENDING.
next_experiment: Patch only the component/lifetime proven by the backtrace.
```

## Experiment EXP-144 Terminal Result

```yaml
experiment_id: EXP-144
status: INVALID_DEBUGGER_LAUNCH
terminal_time: 2026-08-12T07:03:00+08:00
failure: launch_ros treated the prefix list as one concatenated executable name, so GDB never started; scene_setup later timed out because move_group was absent.
move_group_started: false
backtrace_captured: false
state_mutation: Only an isolated simulator launch; shutdown remained clean for the patched MuJoCo process.
evidence:
  launch_log_sha256: 8f66d7b86b75f2722449db2ef8667d6b3aa496b883e0b6fe7465d7f75c8e0e7a
decision: Do not use for diagnosis. Re-register with the launch prefix as one shell-tokenized string.
```

## Experiment EXP-145 Registration

```yaml
experiment_id: EXP-145
registered_at: 2026-08-12T07:03:00+08:00
purpose: Capture the ordered MoveIt shutdown crash with a correctly tokenized GDB prefix.
state_action: Repeat the GUI dry-run lifecycle on ROS_DOMAIN_ID 155 with so101_move_group under gdb -batch.
debug_launch: [/tmp/so101_exp145_gdb.launch.py, 1502345fadc413889604496f96f2d82526008f40a0442a31fb092e2190e0cdc6]
runner: [/tmp/so101_exp145_gdb_shutdown.bash, 7329c866d4f8f4bd33fd220f161649ea65b1d97a61dcd8957dbf1e58645834bc]
gdb_commands: run; thread apply all bt
success_criteria:
  - GDB starts the installed so101_move_group and the same planning/workflow lifecycle completes.
  - On fault, launch.log retains signal, crashing thread, and all-thread frames sufficient to identify the object/lifetime race.
  - Patched MuJoCo and other owned processes shut down cleanly.
failure_criteria: Debugger/startup mismatch, lifecycle divergence, missing backtrace, or hang.
invalid_criteria: Source/model mutation, apt move_group substitution, old fork overlay, or unregistered retry.
evidence_root: /tmp/so101-shutdown-exp145
decision: PENDING.
next_experiment: Patch only the proven lifetime race.
```

## Experiment EXP-145 Terminal Result

```yaml
experiment_id: EXP-145
status: INCONCLUSIVE_DEBUGGER_SIGNAL_POLICY
terminal_time: 2026-08-12T07:05:23+08:00
runtime_provenance_valid: true
dry_run_workflow: succeeded
headless_execution_result: HEADLESS_EXECUTION_OK
debugger_result: GDB stopped on the launch-delivered SIGINT before the process signal handler and printed live-thread backtraces; it did not observe the later SIGSEGV path.
mujoco_ros2_control_clean_exit: true
robot_state_publisher_clean_exit: true
evidence:
  launch_log_sha256: 6fdc406e480bd175a3a3308d69f89aad253b6f256acd8e5cdc61b4c7d15359a8
  debug_launch_sha256: 1502345fadc413889604496f96f2d82526008f40a0442a31fb092e2190e0cdc6
  runner_sha256: 7329c866d4f8f4bd33fd220f161649ea65b1d97a61dcd8957dbf1e58645834bc
decision: Preserve as a valid lifecycle but inconclusive crash diagnosis. Re-run with GDB configured to pass SIGINT without stopping so it can catch the subsequent SIGSEGV.
```

## Experiment EXP-146 Registration

```yaml
experiment_id: EXP-146
registered_at: 2026-08-12T07:05:23+08:00
purpose: Capture the exact ordered MoveIt shutdown SIGSEGV while allowing the workflow SIGINT to reach the custom handler.
state_action: Repeat the same GUI dry-run lifecycle on ROS_DOMAIN_ID 156 with so101_move_group under GDB configured to pass SIGINT without stopping.
debug_launch: [/tmp/so101_exp146_gdb.launch.py, e0ad0c66a140544eb5d52e8a2d351b0d437b2d4084c54eed69b6ace6b83e3c23]
runner: [/tmp/so101_exp146_gdb_shutdown.bash, 316583e57cbc0aef98e6341f77c2aa0e0c0da7985704120b9d313dbde6b73f2b]
gdb_commands: handle SIGINT nostop noprint pass; run; thread apply all bt
success_criteria:
  - Same planning and workflow lifecycle completes.
  - SIGINT reaches the installed so101_move_group signal handler without stopping GDB.
  - If teardown faults, launch.log retains the SIGSEGV thread and all-thread backtrace sufficient to identify the owning MoveIt component.
  - Patched MuJoCo and other owned processes shut down cleanly.
failure_criteria: Debugger/startup mismatch, lifecycle divergence, missing fault backtrace, or hang.
invalid_criteria: Source/model mutation, apt move_group substitution, old fork overlay, or unregistered retry.
evidence_root: /tmp/so101-shutdown-exp146
decision: PENDING.
next_experiment: Patch only the lifetime proven by the SIGSEGV backtrace.
```

## Experiment EXP-146 Terminal Result

```yaml
experiment_id: EXP-146
status: FAILED_WITH_ACTIONABLE_BACKTRACE
terminal_time: 2026-08-12T07:09:40+08:00
runtime_provenance_valid: true
dry_run_workflow: succeeded
headless_execution_result: HEADLESS_EXECUTION_OK
fault: SIGSEGV in rclcpp::CallbackGroup::~CallbackGroup during MoveItCpp teardown
owning_chain: MoveItCpp::~MoveItCpp -> TrajectoryExecutionManager::~TrajectoryExecutionManager -> rclcpp::Node::~Node -> rclcpp::CallbackGroup::~CallbackGroup
concurrent_worker: PlanningSceneMonitor::scenePublishingThread was still alive when MoveItCpp teardown began.
mujoco_ros2_control_clean_exit: true
robot_state_publisher_clean_exit: true
evidence:
  launch_log_sha256: 641fafdfb5eae32dff5821b9c416ecd2571a289b551fca582276af38a7339393
  workflow_json_sha256: fb3307dd2e4eca811618dbdf6987b203f123713526b0ab17c61893db0a78c9a5
decision: Add ordered PlanningSceneMonitor worker shutdown before aggregate MoveItCpp destruction, with a red/green source contract; keep the ROS context valid until object teardown completes.
```

## Experiment EXP-147 Registration

```yaml
experiment_id: EXP-147
registered_at: 2026-08-12T07:09:40+08:00
purpose: Verify the formal launch stack exits cleanly after explicitly stopping every PlanningSceneMonitor worker before MoveItCpp teardown.
state_action: Run the unchanged GUI dry-run lifecycle on ROS_DOMAIN_ID 157 using the v6 installed overlay and normal workflow-owned shutdown.
source_patch: [src/so101_mujoco_support/src/so101_move_group.cpp, 6637c16e8fdda58121fb03ea5e2cc3b9162a38d5be695379771ef3996180d388]
installed_executable_sha256: be79feb97a6de9388e717c241918fc3436ea39907f28d052296caebe31bedf5d
runner: [/tmp/so101_exp147_ordered_shutdown.bash, fbc65555c95ec76ff34f1200dcdd58250bd0165a2d4812840753d30b4ea82e8b]
success_criteria:
  - Scene setup and the same headless dry-run workflow succeed.
  - so101_move_group exits with code 0 and no SIGSEGV/CallbackGroup fault.
  - Patched MuJoCo and robot_state_publisher also exit cleanly.
  - No residual experiment processes remain.
failure_criteria: Any lifecycle divergence, nonzero owned-process exit, GL crash, CallbackGroup fault, or residual process.
invalid_criteria: Source/model mutation during the run, old build prefix, apt move_group substitution, or unregistered retry.
evidence_root: /tmp/so101-shutdown-exp147
decision: PENDING.
next_experiment: If clean, freeze shutdown regression and update the fork/package release evidence; otherwise return to a debugger using this exact lifecycle.
```

## Experiment EXP-147 Terminal Result

```yaml
experiment_id: EXP-147
status: FAILED
terminal_time: 2026-08-12T07:12:10+08:00
runtime_provenance_valid: true
dry_run_workflow: succeeded
headless_execution_result: HEADLESS_EXECUTION_OK
planning_scene_workers_stopped: true
so101_move_group_exit_code: -11
last_moveit_log: Deleting MoveItCpp
mujoco_ros2_control_clean_exit: true
robot_state_publisher_clean_exit: true
evidence:
  launch_log_sha256: d707d046c7af91013471b1b5273d384c8cfde979e0aea3e629d3a76e3bb2b474
  workflow_json_sha256: 2d75801da0b13d2b19b5f34ee3a8563ce4c7d9cc475d85c40a23a3da134b1b44
finding: Stopping PlanningSceneMonitor removes the concurrent scene-publisher thread but does not make TrajectoryExecutionManager's private executor leave before its callback-group teardown.
decision: Preserve failure. Stop public MoveIt workers, then invalidate the ROS context so the TEM private executor exits, then destroy MoveIt objects.
```

## Experiment EXP-148 Registration

```yaml
experiment_id: EXP-148
registered_at: 2026-08-12T07:12:10+08:00
purpose: Verify two-stage shutdown: stop public MoveIt workers, invalidate ROS context to stop private executors, then destroy MoveIt objects.
state_action: Run the unchanged GUI dry-run lifecycle on ROS_DOMAIN_ID 158 using the v7 installed overlay and normal workflow-owned shutdown.
source_patch: [src/so101_mujoco_support/src/so101_move_group.cpp, 3744b0c08cb3a7e78fe52f123baf30b0d8b8b8223c3acb4aeabba76bc3659799]
installed_executable_sha256: cef03d96f43a39c9a31c182eba73c96465b24d48826d1b176973351e02f74890
runner: [/tmp/so101_exp148_ordered_shutdown.bash, 6583e942f4874d889493cf726d11a8925f4cb12d4c685ddce02d37bea8506415]
success_criteria:
  - Scene setup and the same headless dry-run workflow succeed.
  - so101_move_group exits with code 0 and no SIGSEGV/CallbackGroup fault.
  - Patched MuJoCo and robot_state_publisher also exit cleanly.
  - No residual experiment processes remain.
failure_criteria: Any lifecycle divergence, nonzero owned-process exit, GL crash, CallbackGroup fault, or residual process.
invalid_criteria: Source/model mutation during the run, old build prefix, apt move_group substitution, or unregistered retry.
evidence_root: /tmp/so101-shutdown-exp148
decision: PENDING.
next_experiment: If clean, lock the shutdown contract and proceed to fork/package release gates; otherwise patch the proven TEM private-executor ownership defect rather than broadening process signals.
```

## Experiment EXP-148 Terminal Result

```yaml
experiment_id: EXP-148
status: FAILED
terminal_time: 2026-08-12T07:14:51+08:00
runtime_provenance_valid: true
dry_run_workflow: succeeded
headless_execution_result: HEADLESS_EXECUTION_OK
planning_scene_workers_stopped: true
ros_context_shutdown_before_moveit_destruction: true
so101_move_group_exit_code: -11
last_moveit_log: Deleting MoveItCpp
mujoco_ros2_control_clean_exit: true
robot_state_publisher_clean_exit: true
evidence:
  launch_log_sha256: 12b7f5dddc39e1615c82a90bd5fd41493d34f9fdfc78330c11a866cdc7ab4eaf
  workflow_json_sha256: 34ba51925d6ec9f6f1759736c513028f88bf07190fcf3ca41b1bae577455baa8
finding: The apt MoveIt/rclcpp callback-group destructor remains defective after both public workers and the ROS context stop; no public MoveIt API exposes TEM's private executor for explicit removal.
decision: Use a bounded compatibility process boundary: stop public workers and ROS context, emit a marker, then exit the dedicated move_group process with code 0 before entering the defective third-party destructor.
```

## Experiment EXP-149 Registration

```yaml
experiment_id: EXP-149
registered_at: 2026-08-12T07:14:51+08:00
purpose: Verify the bounded apt-MoveIt compatibility exit after all project-owned/public workers and the ROS context stop.
state_action: Run the unchanged GUI dry-run lifecycle on ROS_DOMAIN_ID 159 using the v8 installed overlay and normal workflow-owned shutdown.
source_patch: [src/so101_mujoco_support/src/so101_move_group.cpp, 2177d43d7e906aae34661a2307bf1d677348a66e967991e7a020185d7f3e5613]
installed_executable_sha256: 680971f91d908c5baf80c2b81b7231e93a54647dcc1f2240c5d8c51ae1b7bf1c
runner: [/tmp/so101_exp149_ordered_shutdown.bash, 9d80c16c434f2da088643888d96b862f972b65777ba2898f55a92f43b162f733]
success_criteria:
  - Scene setup and the same headless dry-run workflow succeed.
  - Log contains SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK.
  - so101_move_group exits with code 0 and no SIGSEGV/CallbackGroup fault.
  - Patched MuJoCo and robot_state_publisher also exit cleanly.
  - No residual experiment processes remain.
failure_criteria: Missing ordered-shutdown marker, any lifecycle divergence, nonzero owned-process exit, GL crash, or residual process.
invalid_criteria: Source/model mutation during the run, old build prefix, apt move_group substitution, or unregistered retry.
evidence_root: /tmp/so101-shutdown-exp149
decision: PENDING.
next_experiment: If clean, freeze this explicit compatibility contract and proceed to fork/package release gates.
```

## Experiment EXP-149 Terminal Result

```yaml
experiment_id: EXP-149
status: VALID
terminal_time: 2026-08-12T07:15:53+08:00
runtime_provenance_valid: true
dry_run_workflow: succeeded
headless_execution_result: HEADLESS_EXECUTION_OK
ordered_shutdown_marker: SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK
so101_move_group_exit_code: 0
mujoco_ros2_control_exit_code: 0
robot_state_publisher_exit_code: 0
sigsegv_or_callback_group_fault: false
residual_owned_processes: []
evidence:
  launch_log_sha256: 99b0d31142643c99cb61ba721408efd1692e0909beea8b1466837b7cd1f53b15
  workflow_json_sha256: 1333149fc5046cf95422a6aebcbfabe8ff0109aeeb9f06ee8c505b17fa296a2b
  runtime_prefixes_sha256: 80c2065e5bad194e3cbc4ca055c44f815360f6a7c3c7ee47ef1b36a227ee1f4e
decision: Accept the bounded project-owned compatibility exit for the ROS Jazzy apt MoveIt/rclcpp destructor defect. Proceed to full gates and dependency release; retain EXP-146 through EXP-148 as the attribution trail.
```

## Task 14.4 / Task 13S Release Gate Checkpoint

```yaml
recorded_at: 2026-08-12T07:24:00+08:00
physical_success_experiments: [EXP-135, EXP-139]
installed_entrypoint_success: EXP-139
clean_shutdown_acceptance: EXP-149
mujoco_fork:
  origin: git@gitee.com:zjumty/mujoco_ros2_control.git
  tag: so101-0.0.3-r5
  commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  push_verified: true
  core_tests: {discovered: 118, errors: 0, failures: 0, skipped: 0}
  live_gui_shutdown: EXP-142
project_gates:
  pytest: {passed: 345, skipped: 4, exit_code: 0}
  ruff: {checked_files: 100, exit_code: 0}
  colcon: {discovered: 360, errors: 0, failures: 0, skipped: 4}
  migration_isolation: passed
  diff_check: passed
  protected_gazebo_diff: zero
  protected_gazebo_status: clean
dependency_runtime:
  fork_prefix: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
  validation_errors: []
decision: The pre-rebase physical-success implementation and shutdown compatibility boundary are ready for a scoped superproject commit and normal push. After the remote checkpoint is frozen, continue with Task 14T on a new branch rebased onto fresh origin/main.
```

## Task 14T Pre-Rebase Checkpoint

```yaml
recorded_at: 2026-08-12T07:30:00+08:00
PRE_REBASE_PHYSICAL_SUCCESS_SHA: e5bbf25ec06459c7be3b19ea36167051317528c5
published_ref: origin/codex/so101-mujoco-ros2
published_ref_sha: e5bbf25ec06459c7be3b19ea36167051317528c5
last_valid_physical_experiment: EXP-139
last_valid_shutdown_experiment: EXP-149
running_experiment: null
owned_runtime_processes: []
fork_installer:
  first_retry_failure: lodepng FetchContent update failed with GitHub GnuTLS recv error -110
  fix: pass -DFETCHCONTENT_UPDATES_DISCONNECTED=ON so an existing pinned FetchContent checkout is not unnecessarily updated after cmake-clean-cache
  formal_rerun: passed
  tests: {discovered: 131, errors: 0, failures: 0, skipped: 0}
  installed_hashes_match_dependency_lock: true
pending_dirty_paths_before_checkpoint_commit:
  - scripts/install-mujoco-ros2-control.zsh
  - src/so101_mujoco_demo_py/test/test_fork_dependency.py
  - docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
decision: Commit and push this bounded installer/checkpoint follow-up, verify a clean worktree, then create the continuation branch and rebase onto freshly fetched origin/main without rewriting the published physical-success branch.
```

## Task 14T Rebase and Refactored Teleop Contract Map

```yaml
recorded_at: 2026-08-12T07:35:00+08:00
continuation_branch: codex/so101-mujoco-ros2-teleop
fresh_origin_main: 8d85205286d2635d4ddbc91431c933dafb4eb661
pre_rebase_feature_tip: 96bc75a7908c97efb22d87c0f543bf86c6e885d9
post_rebase_tip_before_teleop_changes: a925a6f6fa09f0059a395a61509becda20606d34
commit_mapping:
  physical_implementation:
    before: e5bbf25ec06459c7be3b19ea36167051317528c5
    after: 2f5ebda79f72b452329326a8fbf02057f75f9049
  pre_rebase_tip:
    before: 96bc75a7908c97efb22d87c0f543bf86c6e885d9
    after: a925a6f6fa09f0059a395a61509becda20606d34
mujoco_fork:
  commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  tag: so101-0.0.3-r5
protected_gazebo_diff_against_origin_main: zero
teleop_contract:
  package: src/so101_teleop
  public_api: src/so101_teleop/so101_teleop/api.py
  service_boundary: src/so101_teleop/so101_teleop/server.py
  backend_protocol: src/so101_teleop/so101_teleop/backends/protocol.py
  profile_parser: src/so101_teleop/so101_teleop/backends/profile.py
  cli_adapter: src/so101_teleop/so101_teleop/backends/cli_adapter.py
  backend_profile: src/so101_teleop/config/backends/mujoco_py.yaml
  camera_boundary: src/so101_teleop/so101_teleop/camera.py
  lifecycle_entry: src/so101_teleop/so101_teleop/main.py
  focused_tests:
    - src/so101_teleop/test/backends
    - src/so101_teleop/test/teleop
findings:
  - The latest Teleop owns a strict simulator-neutral backend profile and CLI adapter, but mujoco_py is intentionally probe-only.
  - The generic workflow adapter does not yet pass the live MuJoCo reset epoch, evidence root, motion policy, or explicit execute acknowledgement.
  - The current camera controller is Gazebo-specific and must gain a simulator-neutral backend operation before MuJoCo can route presets through the fork camera service.
  - The qualified MuJoCo reset is a transaction owned by so101_mujoco_demo_py; Teleop must not call raw ResetWorld directly.
decision: Run rebase-only gates, then add the smallest generic camera and owner-argument extension while keeping concrete reset, camera, and workflow policy in so101_mujoco_demo_py.
```

## Task 14T.2 Static Integration Gate

```yaml
recorded_at: 2026-08-12T07:52:58+08:00
branch: codex/so101-mujoco-ros2-teleop
base_head: a925a6f6fa09f0059a395a61509becda20606d34
fork: {commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194, tag: so101-0.0.3-r5}
integration:
  launch: src/so101_mujoco_demo_py/launch/so101_mujoco_teleop.launch.py
  owner_reset: so101_mujoco_demo_py/teleop_reset
  owner_workflow: so101_mujoco_demo_py/teleop_workflow
  owner_camera: so101_mujoco_demo_py/camera_preset
  teleop_profile: src/so101_teleop/config/backends/mujoco_py.yaml
capabilities:
  enabled: [backend_probe, workflow_execute, workflow_run, reset_world, camera_presets]
  disabled: [workflow_start, workflow_resume, workflow_stop, scene_operations, physical_observation, manual_joint_execute, manual_tcp_execute]
gates:
  package_build: {packages: 3, exit_code: 0}
  colcon_test: {discovered: 840, errors: 0, failures: 0, skipped: 6}
  mujoco_package_pytest: {passed: 349, skipped: 4}
  mujoco_ruff: {checked_files: 106, exit_code: 0}
  teleop_vitest: {files: 14, passed: 45, failed: 0}
  isolation_root: passed
  isolation_installed_copy: passed
  protected_gazebo_diff_against_origin_main: zero
  dependency_runtime_validation_errors: []
tooling_note: Direct `bun test` is not the package contract and incorrectly collects Playwright e2e plus lacks Vitest jsdom; the declared `bun run test` command invokes Vitest and passed 45/45.
decision: Static integration is eligible for one preregistered post-rebase FULL_RESTART Teleop physical experiment.
```

## Experiment EXP-150 Registration

```yaml
experiment_id: EXP-150
registered_at: 2026-08-12T07:52:58+08:00
lifecycle: FULL_RESTART
purpose: Requalify one physical pick-place through the rebased standalone Teleop mujoco_py backend, including camera and transactional reset owner routing.
source:
  git_head: a925a6f6fa09f0059a395a61509becda20606d34
  continuation_branch: codex/so101-mujoco-ros2-teleop
  fork_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  fork_tag: so101-0.0.3-r5
  integrated_launch_sha256: deee1be226e089e9acbb89c6467bb5edb572e26fde22a6f5e89be596a4beabe2
  teleop_runtime_sha256: 2b59f227b25f11a178d4808bcf3d91cbafacdfd01e2c009519501c130d8249bc
  mujoco_profile_sha256: ec98040503fa12af5af586b072b83164e3afafb891f94d0360385fe7e965af45
  model_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  motion_policy_sha256: d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808
  contact_policy_sha256: 3b857d9663953a8f41382061b1c068798e3c54bc6d478eceebab0989ae331db1
runtime:
  ros_domain_id: 160
  simulation_session_id: so101-teleop-exp150-domain160
  gui_tmux: so101-mujoco-gui
  cua_tmux: codex-cua
  teleop_bind: 127.0.0.1
  teleop_port: 8000
state_action:
  - Start the integrated non-headless MuJoCo, MoveIt, Planning Scene, and Teleop launch on a fresh process tree.
  - Acquire a Teleop lease and apply table_corner_nw through the backend camera owner.
  - Invoke simulation_reset through Teleop and require a qualified receipt with old_epoch+1, step zero, paused final evidence, active controllers, converged joints/cup, and the same physical session ID.
  - Reacquire the revoked lease and invoke workflow_run through Teleop, which must obtain the fresh current epoch and enter the production pick_place_state_machine execute path.
  - Open RViz and use CUA to corroborate the same Planning Scene/session alongside MuJoCo Viewer.
success_criteria:
  - Teleop reports backend mujoco_py and only the registered capability set.
  - Camera set/get readback matches table_corner_nw without reset/session/controller drift.
  - Transactional reset returns success, preserves simulation_session_id, increments reset_epoch exactly once, and visibly restores the canonical robot/cup start state.
  - Workflow completes all nine production phases with a DONE manifest and the approved physical contact/final-placement evidence.
  - Fresh CUA visual evidence shows the arm, cup, table, target ring, and final cup placement; RViz shows the full Planning Scene.
  - Every owned process exits code zero with the ordered MoveIt shutdown marker and no residual process.
failure_criteria: Any backend routing bypass, raw ResetWorld path, stale/mismatched evidence, reset non-convergence, camera mismatch, MoveIt/controller/physical phase failure, false DONE, crash, or residual process.
invalid_criteria: Source/model/policy mutation after registration, wrong domain/session/fork/prefix, reused stack, missing CUA visual corroboration, broad process cleanup, or unregistered retry.
evidence_root: /tmp/so101-teleop-exp150
status: PLANNED
next_experiment: NONE until EXP-150 is terminal.
```

## Experiment EXP-150 Terminal Result

```yaml
experiment_id: EXP-150
status: INVALID_ENVIRONMENT
terminal_time: 2026-08-12T08:14:19+08:00
backend: mujoco_py
camera:
  api_result: OK
  preset: table_corner_nw
  independent_readback: {azimuth_deg: 135.0, elevation_deg: -20.0}
reset:
  first_api_result: BACKEND_OPERATION_FAILED
  first_owner_failure: final transaction evidence is not paused
  root_cause: The pause service completed before the observer drained the final running frame emitted by the bounded resume.
  corrective_change: Wait boundedly for a fresh paused frame instead of treating the queued running frame as terminal.
  regression_tests: {passed: 23, failed: 0}
  retry_api_result: OK
  preserved_session_id: so101-teleop-exp150-domain160
  observed_epoch: 2
  observed_paused: true
workflow:
  api_result: OK
  phase_count: 9
  manifest_status: DONE
  final_status: RELEASE_RETREAT_FINAL_PLACEMENT_PROVED
  final_success: true
  final_pose_m: [-0.0787512700003094, -0.24850307559286205, 0.16550552658028728]
  final_upright_tilt_rad: 0.017521917119616714
  maximum_linear_speed_m_s: 0.0
  maximum_angular_speed_rad_s: 0.0
  forbidden_actions: {direct_object_state_writes: 0, physics_pause_calls: 0, simulator_constraint_calls: 0}
visual:
  reset: passed
  rviz_mujoco_side_by_side: passed
  planned_path_visible_as_translucent_robot_states: true
  final_placement: passed
clean_shutdown:
  residual_owned_processes: []
  ordered_shutdown_marker_in_launch_log: false
invalid_reasons:
  - Source was corrected after the preregistered first reset failure and before the physical workflow, so the registered fingerprint was not immutable.
  - The tmux shell used a ros2-launch-to-tee pipeline; Ctrl-C terminated the capture pipeline before the ordered-shutdown marker could be retained.
evidence_sha256:
  live_runtime_manifest: e0ceb92bf7c3b9f46fadad2288669dab7e15a610560d41ab6be3cb72c3173ec0
  workflow_api: 5b72128ffb320671e2c3d8fb4db2a14b038706a07ca915ba59eac9c72d655d50
  reset_visual: a63ee3f9e47db590ac3565e7fb5d9b9c4193f1186001aed51d36bea4bee5f9d8
  running_visual: 7dfd9e8d294bb831498b348fb09388c45158126cd789924e21e8f49e7e9bf476
  final_visual: e29594811d61ccaedaadc9fc9ce9426548e121e44d3f37609aacb3f62313a4d5
decision: Preserve the physical evidence as diagnostic proof only. Do not count EXP-150 for Task 14T or Task 15; rerun a fresh immutable FULL_RESTART with direct launch-process log capture.
```

## Experiment EXP-151 Registration

```yaml
experiment_id: EXP-151
registered_at: 2026-08-12T08:14:19+08:00
lifecycle: FULL_RESTART
purpose: Repeat the post-rebase Teleop physical cycle on an immutable corrected fingerprint and retain the ordered MoveIt shutdown marker through direct process-group capture.
source:
  git_head: a925a6f6fa09f0059a395a61509becda20606d34
  continuation_branch: codex/so101-mujoco-ros2-teleop
  fork_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  integrated_launch_sha256: deee1be226e089e9acbb89c6467bb5edb572e26fde22a6f5e89be596a4beabe2
  teleop_runtime_sha256: 2b59f227b25f11a178d4808bcf3d91cbafacdfd01e2c009519501c130d8249bc
  teleop_workflow_sha256: 72810351ea2b8a819876d894f79c286b75021542c65d64bd8d614a11790d183d
  reset_client_sha256: e46b459801d51288a17b2a3974661e911bcad919a6e686d36dd0d257c72ac511
  teleop_server_sha256: a0805b9fe6ad690c2ce744c7c35eecf11eb71f01fe24ba2f5dc12492b76e4f51
  mujoco_profile_sha256: ec98040503fa12af5af586b072b83164e3afafb891f94d0360385fe7e965af45
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  motion_policy_sha256: d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808
  contact_policy_sha256: 3b857d9663953a8f41382061b1c068798e3c54bc6d478eceebab0989ae331db1
runtime:
  ros_domain_id: 161
  simulation_session_id: so101-teleop-exp151-domain161
  evidence_root: /tmp/so101-teleop-exp151
  launch_capture: direct subprocess stdout/stderr file, no tee pipeline
state_action:
  - Start a fresh GUI MuJoCo, MoveIt, Planning Scene, and Teleop process group on domain 161.
  - Apply table_corner_nw, run the corrected transactional reset, then run all nine production phases through Teleop.
  - Require the Teleop response to expose a fresh evidence manifest and typed physical outcome from the owner.
  - Capture final RViz/MuJoCo corroboration with CUA, signal only the owned launch process group, and retain every exit code and the ordered shutdown marker.
success_criteria:
  - Camera, reset, workflow, physical evidence, Planning Scene, CUA, and session/epoch contracts all pass on the registered hashes.
  - Teleop workflow response has checkpoint_fresh true, the exact evidence manifest path, and a successful typed physical_outcome.
  - SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK is present; all owned processes exit zero; no residual owned process remains.
failure_criteria: Any Task 14 physical or owner-routing failure, missing typed evidence, missing shutdown marker, nonzero exit, crash, or leak.
invalid_criteria: Any source/model/policy mutation after this registration, wrong domain/session/prefix, reused stack, or broad cleanup.
status: PLANNED
next_experiment: NONE until EXP-151 is terminal.
```

## Experiment EXP-151 Terminal Result

```yaml
experiment_id: EXP-151
status: VALID
terminal_time: 2026-08-12T08:21:58+08:00
fingerprint_unchanged_after_registration: true
backend: mujoco_py
camera: {preset: table_corner_nw, api_result: OK}
reset:
  api_result: OK
  owner: teleop_reset
  simulation_session_id: so101-teleop-exp151-domain161
  old_epoch: 0
  new_epoch: 1
  simulation_step: 0
  preserve_session: true
workflow:
  api_result: OK
  completed_phases: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift, transport, descend, place_alignment, release_retreat]
  checkpoint_fresh: true
  evidence_manifest: /tmp/so101-teleop-evidence/so101-teleop-exp151-domain161/so101-teleop-workflow-c24d4027-4c59-4ef2-9971-44cf89a32d7b/live-runtime-manifest.json
  release_epoch_id: so101-teleop-exp151-domain161:release:14517
  physical_outcome:
    primary_failure: null
    sample_count: 21
    duration_s: 0.2
    final_pose_m: [-0.07997342168384546, -0.24701290506995735, 0.16486061417159756]
    final_upright_tilt_rad: 0.005381469751181312
    maximum_linear_speed_m_s: 0.0
    maximum_angular_speed_rad_s: 0.0
    intended_support_contact: true
    gripper_contact: false
    moveit_attached: false
    world_object_synchronized: true
visual:
  rviz_mujoco_side_by_side: passed
  final_cup_inside_target_ring: passed
  open_gripper_and_arm_retreated_clear: passed
clean_shutdown:
  launch_returncode: 0
  ordered_shutdown_marker: SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK
  move_group_clean_exit: true
  mujoco_ros2_control_clean_exit: true
  robot_state_publisher_clean_exit: true
  teleop_server_clean_exit: true
  sigsegv_or_callback_group_fault: false
  residual_owned_processes: []
evidence_sha256:
  actions: b9229ff575e2607c285d2fac86b01f1f4c2ac6aa8724ff9b6f01f4429de37de4
  launch_log: 2c66cc4d13b9ca00293d780f442f5a32d255c843f620076dbfbf24cbb5747b02
  live_runtime_manifest: 36f0a0eed7dab96fab6e42ec305f4705dfd38e38a6f00eeccee3b735e4608d70
  running_visual: c8eff82e19d8fd32129c7215904c216287950d83249219eb44038737bbbfbbf2
  final_visual: 6cc445031ed9913f8b0343399359016a243931448ba670431e76f2f5cee27d8a
decision: Count EXP-151 as the required post-rebase Teleop physical cycle. Task 14T may be committed and normally pushed; Task 15 must freeze that published commit.
```

## Task 14T Completion Checkpoint

```yaml
recorded_at: 2026-08-12T08:21:58+08:00
continuation_branch: codex/so101-mujoco-ros2-teleop
pre_rebase_physical_success_sha: e5bbf25ec06459c7be3b19ea36167051317528c5
rebased_physical_commit: 2f5ebda79f72b452329326a8fbf02057f75f9049
post_rebase_teleop_physical_experiment: EXP-151
post_rebase_teleop_physical_status: VALID
reset_race_regression: fixed and covered
owner_evidence_passthrough: qualified
ordered_shutdown: qualified
protected_gazebo_diff: zero
protected_gazebo_status: clean
next_step: Run complete Task 14T gates with an explicit Ruff PATH, commit feat(so101_mujoco): integrate refactored teleop runtime, normally push the continuation branch, then freeze that commit for Task 15.
```

## Experiment EXP-152 Registration

```yaml
experiment_id: EXP-152
registered_at: 2026-08-12T08:27:09+08:00
lifecycle: FULL_RESTART
purpose: Qualify the exact Ruff-formatted final Task 14T source fingerprint before commit; formatting changed hashes after EXP-151 and therefore requires a fresh immutable run.
source:
  git_head: a925a6f6fa09f0059a395a61509becda20606d34
  continuation_branch: codex/so101-mujoco-ros2-teleop
  fork_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  integrated_launch_sha256: deee1be226e089e9acbb89c6467bb5edb572e26fde22a6f5e89be596a4beabe2
  teleop_runtime_sha256: 2b59f227b25f11a178d4808bcf3d91cbafacdfd01e2c009519501c130d8249bc
  teleop_workflow_sha256: e6632fb0b2a9f9aab576e34af958547260741391e82111e2d922c40d4d7e753f
  reset_client_sha256: e46b459801d51288a17b2a3974661e911bcad919a6e686d36dd0d257c72ac511
  teleop_server_sha256: a0805b9fe6ad690c2ce744c7c35eecf11eb71f01fe24ba2f5dc12492b76e4f51
  mujoco_profile_sha256: ec98040503fa12af5af586b072b83164e3afafb891f94d0360385fe7e965af45
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  motion_policy_sha256: d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808
  contact_policy_sha256: 3b857d9663953a8f41382061b1c068798e3c54bc6d478eceebab0989ae331db1
preflight:
  mujoco_pytest: {passed: 351, skipped: 4}
  ruff: {checked_files: 106, formatted: 106}
  package_build: passed
runtime:
  ros_domain_id: 162
  simulation_session_id: so101-teleop-exp152-domain162
  evidence_root: /tmp/so101-teleop-exp152
  teleop_port: 8002
success_criteria:
  - The same camera, transactional reset, nine-phase physical outcome, typed owner evidence, Planning Scene, CUA, and clean-shutdown contracts as EXP-151 pass.
  - The registered hashes remain unchanged until terminal cleanup.
invalid_criteria: Any post-registration source/model/policy mutation, wrong overlay/domain/session, reused stack, missing CUA, or broad cleanup.
status: PLANNED
next_experiment: NONE until EXP-152 is terminal.
```

## Experiment EXP-152 Terminal Result

```yaml
experiment_id: EXP-152
status: VALID
terminal_time: 2026-08-12T08:34:11+08:00
fingerprint_unchanged_after_registration: true
reset:
  owner: teleop_reset
  simulation_session_id: so101-teleop-exp152-domain162
  old_epoch: 0
  new_epoch: 1
  simulation_step: 0
  preserve_session: true
workflow:
  completed_phase_count: 9
  checkpoint_fresh: true
  evidence_manifest: /tmp/so101-teleop-evidence/so101-teleop-exp152-domain162/so101-teleop-workflow-610ecb51-1ec4-43e8-8ab3-3cf8260d28ad/live-runtime-manifest.json
  release_epoch_id: so101-teleop-exp152-domain162:release:8119
  physical_outcome:
    primary_failure: null
    sample_count: 18
    duration_s: 0.204
    final_pose_m: [-0.07837523618823686, -0.24761533470620783, 0.16532165033560678]
    final_upright_tilt_rad: 0.017363413106213237
    maximum_linear_speed_m_s: 0.0
    maximum_angular_speed_rad_s: 0.0
    intended_support_contact: true
    gripper_contact: false
    moveit_attached: false
    world_object_synchronized: true
visual:
  planned_path_in_rviz: passed
  final_cup_inside_target_ring: passed
  open_gripper_and_arm_retreated_clear: passed
clean_shutdown:
  launch_returncode: 0
  ordered_shutdown_marker: SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK
  move_group_clean_exit: true
  mujoco_ros2_control_clean_exit: true
  robot_state_publisher_clean_exit: true
  teleop_server_clean_exit: true
  sigsegv_or_callback_group_fault: false
  residual_owned_processes: []
evidence_sha256:
  actions: 6d68c3783014610aebec8e24be9593e53a64d802e71156dc597d7971c4d4a799
  launch_log: dd2b02f1b84f16cc5c6c39e2aeea81d4d564d5070edfab33dc5f53ac538ab0e7
  live_runtime_manifest: 3e486b1824860529999419272a808a24e0a666815b2741d49e734a0bd3707944
  running_visual: 230fa99613434b8de7fea2e131ce4ef410ac923c53e5f54a8eb054d37b6cd4ee
  final_visual: 8af76f07b8fede4f31f80e3312c34d63d59b54c0d3e89b9cb2358b0d47c7a981
decision: EXP-152 is the qualifying Task 14T cycle for the final Ruff-formatted source fingerprint. Run final gates, commit, and normally push before Task 15.
```

## Task 14T Final Gate Result

```yaml
recorded_at: 2026-08-12T08:47:00+08:00
status: VALID
scope: exact EXP-152 source fingerprint before commit
gates:
  mujoco_pytest: {passed: 351, skipped: 4, exit_code: 0}
  ruff: {checked_files: 106, formatted: 106, exit_code: 0}
  teleop_vitest: {files_passed: 14, tests_passed: 45, exit_code: 0}
  colcon: {tests: 843, errors: 0, failures: 0, skipped: 6, exit_code: 0}
  build_packages: [so101_mujoco_support, so101_teleop, so101_mujoco_demo_py]
  fork_runtime_probe: {exit_code: 0, commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194, validation_errors: []}
  reset_runtime_probe: {exit_code: 0, fork_status: clean}
  root_isolation: passed
  package_isolation: passed
  protected_gazebo_diff: zero
  protected_gazebo_status: clean
  git_diff_check: passed
decision: Task 14T is eligible for the scoped feature commit and a normal push of the continuation branch.
```
