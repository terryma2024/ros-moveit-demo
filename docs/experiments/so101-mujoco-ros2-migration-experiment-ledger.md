---
task_id: so101-mujoco-ros2-migration
goal: Replace the Gazebo Python demonstration with an independently packaged MuJoCo ROS 2 demonstration.
success_contract: The MuJoCo implementation satisfies its ROS 2 and physical outcome contracts without changing or depending on the protected Gazebo Python tree.
main_base_commit: d300e7a41fb274d6d7e120699b7040666ea61904
task_base_commit: 45c6efc701b133c45875e86b0053cfc37dab7f4f
behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
rejected_backup_commit: 3add34f8390b78a1f4a13ff49aefb2dc87638245
rejected_backup_branch: codex/so101-mujoco-ros2-pre-isolation-20260810
branch: codex/so101-mujoco-ros2
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
base_commit: d300e7a41fb274d6d7e120699b7040666ea61904
last_verified_implementation_commit: 997e8ed95100e4097744c92f1b065613ab390220
ledger_commit_pending: true
task_status: TASK_13_IMPLEMENTATION_PENDING_COMMIT
evidence_root: /tmp/so101-debug-mujoco-migration/
protected_nontracked_baseline_sha256: 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f
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
disproven_routes:
  - The pre-isolation backup is provenance only and is not an implementation source; CP-001.
open_hypotheses:
  - NONE; Task 12 implementation still requires final offline gates and review before its scoped commit.
latest_checkpoint: CP-091
next_experiment: EXP-057
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
