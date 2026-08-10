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
last_verified_implementation_commit: c9ab83d0a94311a10db824841c9a36aa44e89c49
ledger_commit_pending: false
task_status: TASK_11_COMPLETE
evidence_root: /tmp/so101-debug-mujoco-migration/
protected_nontracked_baseline_sha256: 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f
strict_physics_contract: The successful positive path must use physical contact and grasp forces with no weld, no equality constraint, no adhesion or adhesive actuator, no mocap body, no teleport or set-pose, no direct object qpos writes, and no direct object qvel writes.
confirmed_conclusions:
  - The rebased migration starts from the exact main baseline; CP-001.
disproven_routes:
  - The pre-isolation backup is provenance only and is not an implementation source; CP-001.
open_hypotheses:
  - The behavior source can be migrated to MuJoCo while preserving the strict no-weld/no-teleport contract.
latest_checkpoint: CP-047
next_experiment: EXP-035
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
