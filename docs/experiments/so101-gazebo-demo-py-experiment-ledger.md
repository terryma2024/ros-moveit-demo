# SO-101 standalone Python rewrite experiment ledger

```yaml
task_id: so101-gazebo-demo-py
goal: Complete standalone Python rewrite with physical pre-attach micro-lift and headless/GUI acceptance.
success_contract: Fresh execute reaches DONE with unchanged main-workspace contact materials and grasp policy; 2 mm pre-attach object lift; separate Gazebo and MoveIt attach/detach; controller/joint/TF, final pose, and visual proof.
worktree: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py
branch: codex/so101-gazebo-demo-py
base_commit: 90c6c11
current_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a
evidence_root: /tmp/so101-py-g7LydYCB/
confirmed_conclusions:
  - Built-in DetachableJoint attach/detach works after bilateral contact; earlier Task 8 run attached before micro-lift and therefore did not prove the approved pre-attach micro-lift gate.
  - With the current Python live sequence, contact-missing retries can establish bilateral contact within the unchanged 4 mrad cumulative tightening cap.
  - With fixed 6 mrad seating preload, the detached object lifted only 0.000003 m versus the required 0.002 m in historical run task15-e2e-7.
disproven_routes:
  - Treating post-attachment object following as proof of the pre-attachment physical micro-lift gate.
  - Adding the already-approved fixed 6 mrad preload to the Python sequence without first matching main-workspace command ordering and observation windows.
open_hypotheses:
  - Python live orchestration differs from main-workspace grasp sequencing or stable-window timing despite matching policy values.
  - Prepared SDF/controller/runtime assets differ from the current main workspace even though copied provenance was correct at the earlier reference commit.
latest_checkpoint: CP-002
next_experiment: EXP-007
```

## Historical evidence imported before ledger activation

- `task15-e2e-2`: INVALID environment run; ROS domain 249 exceeded Fast DDS port range. Evidence: `/tmp/so101-py-g7LydYCB/task15-e2e-2/`.
- `task15-e2e-3`: VALID boundary failure; fixed finger contact existed, moving jaw was missing, no attachment was commanded. Evidence: `/tmp/so101-py-g7LydYCB/task15-e2e-3/state-machine.txt`.
- `task15-e2e-4`: VALID boundary failure; bounded retry established bilateral contact, but detached object lift was about 0.000001 m. Evidence: `/tmp/so101-py-g7LydYCB/task15-e2e-4/state-machine.txt`.
- `task15-e2e-5`: INVALID due to two concurrent execute clients after a mistaken process-liveness inference; excluded from behavior conclusions.
- `task15-e2e-7`: VALID boundary failure; one execute client, fixed 6 mrad seating preload, detached object lift `0.000003 m`, lateral drift `0.000001414 m`, then safe stop before attachment. Evidence: `/tmp/so101-py-g7LydYCB/task15-e2e-7/state-machine.txt`.

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: task15-e2e-7
hypothesis: The first divergence is an implementation or asset mismatch between the current main workspace and the Python rewrite, not friction/material/policy tuning.
prediction: A read-only normalized comparison will identify at least one difference in command ordering, stable-window logic, retry/preload targets, micro-lift target, controller configuration, collision geometry, or SDF contact material.
single_variable: NONE; read-only comparison of current main workspace against Python rewrite.
lifecycle: FULL_RESTART
preconditions:
  - No new ROS/Gazebo/MoveIt stack is started.
  - Main workspace is read only and remains clean at commit 05dff7a18e466c01486441dd90c21fcd44d4d8cd.
  - Python worktree dirty paths are exactly the uncommitted Task 15 implementation plus this ledger.
success_criteria:
  - Produce hashes/diffs for relevant assets and an exact sequence comparison with source line evidence.
failure_criteria:
  - No difference is found in the compared boundaries; next hypothesis must move to runtime observation timing.
invalid_criteria:
  - Either source tree changes during capture or comparison includes an unrelated worktree as the reference.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install/so101_gazebo_demo_py/lib/so101_gazebo_demo_py/pick_place_state_machine
  ros_domain_id: NONE
  gz_partition: NONE
commands:
  - command: read-only rg/diff/hash comparison against /data/work/ws_moveit/src/so101_gazebo_demo
    exit_code: 0
observed:
  - OBSERVED main workspace is main@05dff7a18e466c01486441dd90c21fcd44d4d8cd and clean.
  - OBSERVED world SDF SHA-256 is identical in both packages: 386f293037aa0c38687803b21a2989901f7c33b84adc553ea7306c780f6386f2.
  - OBSERVED main motion policy uses DESCEND endpoint [-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465] and has no CLOSE_GRIPPER motion state; Python retained the old endpoint plus a separate CLOSE_GRIPPER target.
  - OBSERVED main stabilizer requires six consecutive bilateral samples, commands exactly q6_contact minus 0.006 once, then requires six new bilateral samples. Python live code combined up to 0.004 contact-missing tightening with an additional 0.006 preload.
  - OBSERVED main micro-lift plans from the observed TCP pose to world Z plus 0.002 through MoveIt; Python live code used an old fixed joint target.
  - OBSERVED controller arm path tolerance changed from 0.008 to 0.012; carrying/place motion scalings also changed.
inferred:
  - INFERRED the 0.000003 m failure does not test the current main-workspace strategy because both the seated arm endpoint and micro-lift request construction differ.
conclusion: The first divergence is stale strategy/configuration and fixed-joint micro-lift implementation, not a need to tune friction or contact materials.
evidence:
  - /tmp/so101-py-g7LydYCB/
decision: KEEP
next_experiment: EXP-007
```

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-006
hypothesis: Exact alignment to main@05dff7a of seated DESCEND, six-sample fixed preload, and current-TCP MoveIt world-Z micro-lift will restore the 2 mm detached-cup lift without changing friction, materials, q6 bounds, or assertions.
prediction: A fresh FULL_RESTART run reaches pre-attach cup world-Z delta at least 0.002 m with bilateral contact and moving-pad depth at most 0.0013 m while attachment remains detached.
single_variable: Replace stale Python grasp sequence/config with the current main-workspace sequence/config; no physics/material change.
lifecycle: FULL_RESTART
preconditions:
  - All prior Python-owned Gazebo servers are stopped by exact PID.
  - No unrelated Gazebo, move_group, or pick_place process is used.
  - Source and installed assets are proven from this worktree after rebuild.
success_criteria:
  - Six consecutive bilateral stable samples before and after one fixed 6 mrad preload.
  - Current-TCP MoveIt world-Z request executes and TCP rises 0.002 m within tolerance.
  - Detached cup rises at least 0.002 m with lateral slip at most 0.001 m.
failure_criteria:
  - Valid fresh run stops at any earlier boundary or cup lift remains below 0.002 m.
invalid_criteria:
  - Duplicate execute clients, invalid ROS domain, stale installed assets, or non-clean initial world.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted EXP-007 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install/so101_gazebo_demo_py/lib/so101_gazebo_demo_py/pick_place_state_machine
  ros_domain_id: 181
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: PYTHONPATH=src/so101_gazebo_demo_py python3 -m pytest -q test_main_strategy_parity.py test_provenance.py test_policy_config.py
    exit_code: 0 (10 passed)
  - command: colcon build/test --packages-select so101_gazebo_demo_py
    exit_code: 0 (80 passed, 2 skipped)
  - command: ROS_DOMAIN_ID=181 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-8
    exit_code: 1 at live execute (driver status capture was unreliable because of the wrapper pipeline)
observed:
  - OBSERVED no attach command occurred after the grasp attempt.
  - OBSERVED fixed preload was incorrectly derived from grasp_close_q6, producing -0.053608632840292 rather than observed q6_contact minus 0.006.
  - OBSERVED gripper_controller aborted that goal after goal_time_tolerance exceeded by 1.001 seconds.
inferred:
  - INFERRED the world-Z micro-lift remains untested in this run because the first divergence is q6-contact capture.
conclusion: Exact strategy parity additionally requires sampling the achieved q6 at contact; the policy constant is not the contact observation.
evidence:
  - /tmp/so101-py-g7LydYCB/
decision: ITERATE
next_experiment: EXP-008
```

```yaml
experiment_id: EXP-008
status: VALID
prior_experiment: EXP-007
hypothesis: Sampling achieved q6_contact before applying the single fixed 0.006 preload will pass the gripper boundary and reach the unchanged 2 mm physical micro-lift assertion.
prediction: A fresh isolated run commands seating_target_q6 equal to observed q6_contact minus 0.006 (bounded only by the existing q6 floor), then either proves the detached 2 mm cup lift or exposes the next first boundary.
single_variable: Replace policy-constant preload input with the observed joint 6 contact position.
lifecycle: FULL_RESTART
preconditions:
  - EXP-007 owned stack is fully stopped.
  - World SDF/material hash remains 386f293037aa0c38687803b21a2989901f7c33b84adc553ea7306c780f6386f2.
success_criteria:
  - Gripper preload succeeds and detached cup world-Z delta is at least 0.002 m with lateral drift at most 0.001 m.
failure_criteria:
  - Any earlier boundary fails or the unchanged physical assertion fails.
invalid_criteria:
  - Duplicate execute clients, stale install, or non-isolated ROS/Gazebo identity.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 182
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=182 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-9
    exit_code: 1 at live execute (wrapper pipeline incorrectly recorded 0)
observed:
  - OBSERVED no physical attachment command occurred after the grasp attempt.
  - OBSERVED the observed-contact q6 preload goal succeeded, followed by six stable bilateral samples.
  - OBSERVED the current-TCP world-Z MoveIt motion executed successfully.
  - OBSERVED detached cup world-Z delta was 0.0018129999999999813 m and lateral drift was 0.00031739722746112087 m.
  - OBSERVED the unchanged >=0.002 m physical assertion failed before attachment.
conclusion: The exact main@05dff7a strategy and identical material/world assets still do not satisfy the approved strict 0.002 m detached-cup lift assertion in this standalone runtime.
decision: STOP_AT_TASK_8_GATE
next_experiment: Requires a user design decision; do not continue downstream.
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-008
current_hypothesis: NONE; the documented hard gate is contradicted by a valid fresh runtime result.
working_tree_status: Task 15 recalibration/live implementation and experiment evidence remain uncommitted.
owned_processes: NONE after the isolated runner cleanup.
preserved_processes: codex and codex-cua tmux; unrelated clang-tidy processes.
confirmed_conclusions:
  - Main and Python world SDF/friction/material assets are byte-identical.
  - Main seated endpoint, controller tolerance, contact-stability window, observed-q6 fixed preload, and current-TCP world-Z request are aligned.
  - Detached cup lift is 0.0018129999999999813 m, below the immutable 0.002 m assertion.
disproven_routes:
  - Stale strategy/config alone does not recover the strict physical gate.
open_risks:
  - Task 15 headless E2E and Task 16 GUI acceptance must not run through the failed gate.
next_command: Await the minimal design decision required by the Task 8 gate.
```

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-008
hypothesis: The 0.001813 m observation was taken before the required WAIT_MICRO_LIFT_STABLE boundary; six post-motion bilateral samples will provide the authoritative stable cup displacement without changing the 2 mm command or any assertion.
prediction: A fresh isolated run preserves bilateral contact for six consecutive post-lift samples and then reports detached cup lift >=0.002 m, or identifies a stable physical failure with better boundary evidence.
single_variable: Add the missing post-micro-lift six-sample bilateral stability wait before the after-pose sample.
lifecycle: FULL_RESTART
preconditions:
  - No prior owned stack remains.
  - World SDF/material hash remains unchanged.
  - Micro-lift command remains exactly 0.002 m and all physical ceilings/assertions remain unchanged.
success_criteria:
  - Detached cup lift >=0.002 m, lateral drift <=0.001 m, bilateral stable contact, no attachment before proof.
failure_criteria:
  - Stable contact or unchanged physical assertion fails.
invalid_criteria:
  - Duplicate execute clients, stale install, or non-isolated runtime.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 183
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=183 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-10
    exit_code: 1 at unchanged lateral-drift assertion
observed:
  - OBSERVED six post-motion contact probes took approximately 18 seconds because each probe aggregated for its full 3-second deadline.
  - OBSERVED stable detached cup lift was 0.0021730000000000083 m.
  - OBSERVED lateral drift was 0.0016898499933426041 m, exceeding the unchanged 0.001 m assertion.
conclusion: The missing stable boundary recovered Z lift, but the Python contact probe implements a 3-second window rather than one fresh sample and introduces excessive dwell/slip.
decision: ITERATE
next_experiment: EXP-010
```

```yaml
experiment_id: EXP-010
status: VALID
prior_experiment: EXP-009
hypothesis: Returning each contact probe after its first fresh nonempty message will preserve six consecutive samples while eliminating the 18-second dwell that caused lateral slip.
prediction: A fresh run reaches detached cup lift >=0.002 m and lateral drift <=0.001 m after six fast post-lift samples.
single_variable: End each contact probe on the first decoded fresh nonempty contact message instead of waiting the full 3-second deadline.
lifecycle: FULL_RESTART
preconditions:
  - No prior owned stack remains.
  - Same 2 mm command, materials, q6 target, six-sample count, and assertions.
success_criteria:
  - Strict physical gate passes before attachment.
failure_criteria:
  - Any unchanged physical assertion fails.
invalid_criteria:
  - Duplicate runtime, stale install, or empty/old contact messages counted as fresh.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 184
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=184 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-11
    exit_code: 1 at unchanged lateral-drift assertion
observed:
  - OBSERVED detached cup lift was 0.003493999999999997 m and lateral drift was 0.0016114713773443133 m.
  - OBSERVED fast contact sampling did not restore pose-constrained motion behavior.
conclusion: Sampling latency is not the upstream cause; Python's IK-to-wide-joint-goal micro-lift differs architecturally from the main pose-constrained MoveGroup request.
decision: REPLACE_ARCHITECTURAL_MISMATCH
next_experiment: EXP-011
```

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: The IK plus 0.03-rad joint-goal path causes endpoint/path drift; the main-equivalent MoveGroup pose constraint with 0.0002 m position and 0.005 rad orientation tolerance will keep the 2 mm world-Z probe within lateral bounds.
prediction: A fresh run plans through /move_action with the exact pose tolerances, executes the returned trajectory, and passes detached lift/lateral assertions.
single_variable: Replace IK plus joint-goal planning with request-scoped pose-constrained MoveGroup planning.
lifecycle: FULL_RESTART
preconditions:
  - No prior owned stack remains.
  - Same contacts, 2 mm displacement, materials, q6 target, and assertions.
success_criteria:
  - Detached cup lift >=0.002 m and lateral drift <=0.001 m before attachment.
failure_criteria:
  - MoveGroup pose planning/execution or any unchanged physical assertion fails.
invalid_criteria:
  - Duplicate runtime or stale installed Python module.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 185
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=185 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-12
    exit_code: 1 at MOVE_ABOVE_PLACE controller path tolerance
observed:
  - OBSERVED the pose-constrained micro-lift passed all unchanged physical assertions and execution continued through attachment and LIFT.
  - OBSERVED the first downstream failure was MOVE_ABOVE_PLACE with controller error -4, path tolerance violation.
conclusion: The Task 8 physical gate is passed by the main-equivalent pose-constrained MoveGroup request; carrying trajectories still ignore their policy velocity scaling.
decision: KEEP_AND_ADVANCE_TO_DOWNSTREAM_FIX
next_experiment: EXP-012
```

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: Applying each state's configured velocity scaling to the fixed waypoint timing will prevent the carrying path-tolerance violation.
prediction: MOVE_ABOVE_PLACE at 0.02 scaling uses 5 seconds per waypoint and reaches the next boundary; physical-gate.json is persisted before attachment.
single_variable: Derive waypoint duration from the existing per-state velocity scaling.
lifecycle: FULL_RESTART
preconditions:
  - Pose-constrained physical gate retained unchanged.
  - No prior owned runtime remains.
success_criteria:
  - Strict physical gate evidence persists and uninterrupted execute reaches DONE.
failure_criteria:
  - First new downstream boundary fails.
invalid_criteria:
  - Duplicate runtime or stale install.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 186
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=186 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-13
    exit_code: 1 at pre-attach bilateral stability
observed:
  - OBSERVED moving-jaw contact was absent after seating; fixed-finger depth was 0.0011608890490606427 m.
  - OBSERVED the carrying-timing hypothesis was not reached.
conclusion: The live executor lacks the approved bounded contact-missing retry path, so a transient unilateral grasp aborts before the carrying experiment.
decision: IMPLEMENT_REQUIRED_RETRY
next_experiment: EXP-013
```

```yaml
experiment_id: EXP-013
status: VALID
prior_experiment: EXP-012
hypothesis: The approved maximum of four 1 mrad contact-missing retries will recover transient unilateral grasps and allow the already-slowed carrying path to execute.
prediction: A fresh run either establishes bilateral contact within five total attempts and reaches DONE, or preserves the fifth exact physical failure.
single_variable: Add bounded contact-missing preopen/reclose retries, cumulative tightening capped at 4 mrad and q6 safe floor.
lifecycle: FULL_RESTART
preconditions:
  - No prior owned runtime remains.
  - Six-sample stability, fixed seating preload, materials, and assertions unchanged.
success_criteria:
  - physical-gate.json proves pre-attach gate and uninterrupted run reaches DONE.
failure_criteria:
  - Fifth grasp attempt or a later boundary fails.
invalid_criteria:
  - More than five total attempts, more than 4 mrad tightening, duplicate runtime, or stale install.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 187
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=187 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-14
    exit_code: 1 at post-micro-lift bilateral stability
observed:
  - OBSERVED initial bilateral stability was recovered, but after micro-lift fixed-finger contact was absent while moving-jaw contact remained.
  - OBSERVED no attachment occurred.
conclusion: Retry must cover the complete physical attempt, including micro-descend and reclose after a post-lift contact failure.
decision: EXTEND_EXISTING_FIVE_ATTEMPT_BUDGET
next_experiment: EXP-014
```

```yaml
experiment_id: EXP-014
status: VALID
prior_experiment: EXP-013
hypothesis: Applying the same five-attempt budget to complete stabilize/lift attempts, with micro-descend before retry, will recover post-lift contact loss without exceeding the approved bounds.
prediction: A fresh run either proves the strict gate within five complete attempts and reaches the next downstream boundary, or preserves the fifth failure.
single_variable: Extend retry scope across the complete physical attempt; budgets and increments unchanged.
lifecycle: FULL_RESTART
preconditions:
  - No owned runtime remains.
  - Maximum five attempts, 4 mrad tightening, exact 2 mm moves, unchanged physical assertions.
success_criteria:
  - physical-gate.json is PROVED and uninterrupted execute reaches DONE.
failure_criteria:
  - Fifth physical attempt or later boundary fails.
invalid_criteria:
  - Budget violation, duplicate runtime, or stale install.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 188
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=188 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-15
    exit_code: 1 at contact-stopped gripper result classification
observed:
  - OBSERVED retry reclose reached physical contact but controller returned error -5 after numerical goal tolerance exceeded by 1.002 seconds.
  - OBSERVED the live backend rejected the result without applying the main contact-stopped success contract.
conclusion: q6 contact-stop classification is missing from the Python live adapter.
decision: IMPLEMENT_CONTACT_STOP_SEMANTICS
next_experiment: EXP-015
```

```yaml
experiment_id: EXP-015
status: VALID
prior_experiment: EXP-014
hypothesis: Accepting controller -5 only when fresh bilateral contact is present and within the immutable solver-depth ceiling will preserve q6 semantics and allow bounded retry to continue.
prediction: Contact-stopped retry commands are accepted only with safe bilateral evidence and the run reaches the strict gate or a later boundary.
single_variable: Add evidence-gated contact-stopped result classification.
lifecycle: FULL_RESTART
preconditions:
  - No prior owned runtime remains; numerical q6 goals and all physical bounds unchanged.
success_criteria:
  - physical-gate.json is PROVED and uninterrupted run reaches DONE.
failure_criteria:
  - Fifth attempt or later boundary fails.
invalid_criteria:
  - Any aborted gripper goal accepted without fresh safe bilateral evidence.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus uncommitted Task 15 patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 189
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=189 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-16
    exit_code: 1 at downstream LIFT, but physical gate record is CONTRADICTED by the independent ceiling
observed:
  - OBSERVED bounded retry attempt 2 produced cup Z lift 0.0021569999999999923 m and lateral drift 0.0001562465999630221 m while detached.
  - OBSERVED moving-pad penetration was 0.001072108163498342 m, exceeding the immutable 0.000800002 m ceiling.
  - OBSERVED the then-current code incorrectly wrote status PROVED and attached; the next LIFT failed at 0.012306 rad against the unchanged 0.012 rad path tolerance.
  - OBSERVED the source is now patched fail-closed to reject penetration above 0.000800002 m before attachment; 11 targeted tests pass and package rebuild succeeds.
conclusion: The approved 1 mrad contact-missing tightening can recover lift/contact, but in this runtime it violates the independent moving-pad ceiling. It cannot be accepted or retracted after the fact without authorizing a changed retry strategy.
decision: STOP_AT_TASK_8_GATE
next_experiment: Requires a design decision on retry strategy that preserves the 0.000800002 m ceiling.
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-015
current_hypothesis: A different arm seating/retry strategy may establish fixed contact without the 1 mrad squeeze exceeding the moving-pad ceiling.
working_tree_status: Uncommitted Task 15 implementation, fail-closed ceiling fix, tests, provenance updates, and ledger.
owned_processes: NONE after isolated runner cleanup.
preserved_processes: codex, codex-cua, and unrelated clang-tidy processes.
confirmed_conclusions:
  - Materials/world assets remain byte-identical to main@05dff7a.
  - Pose-constrained 2 mm MoveGroup execution fixes the prior Z/lateral motion mismatch.
  - Retry attempt 2 passes lift/lateral but violates moving-pad ceiling by 0.000272106 m.
disproven_routes:
  - Accepting controller contact-stop solely under the 0.0013 m solver limit is unsafe for this gate.
  - Slower/faster evidence sampling does not resolve the strategy conflict.
open_risks:
  - No acceptable attachment may occur until bilateral contact, lift/lateral, and 0.000800002 m ceiling pass simultaneously.
next_command: Await authorization for a retry strategy deviation, such as arm reseating without additional q6 squeeze.
```

```yaml
experiment_id: EXP-016
status: VALID
prior_experiment: EXP-015
hypothesis: A bounded 0.2 mm TCP local +X reseat per retry can restore fixed-finger contact while keeping q6 at its initial seating target and moving-pad penetration <=0.000800002 m.
prediction: Within five total attempts and 0.8 mm cumulative reseat, a fresh run simultaneously passes bilateral contact, 2 mm lift, lateral drift, and the immutable moving-pad ceiling.
single_variable: Replace retry q6 tightening with bounded local +X arm reseating; all other strategy and physics unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Explicit user authorization received.
  - Fail-closed ceiling check installed; q6 target does not tighten on retry.
success_criteria:
  - physical-gate.json proves all strict criteria before attachment and run reaches the next boundary.
failure_criteria:
  - Fifth attempt or any later boundary fails.
invalid_criteria:
  - q6 target changes, cumulative reseat exceeds 0.8 mm, stale install, or duplicate runtime.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus authorized uncommitted strategy patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 170
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=170 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-17
    exit_code: 1 after fifth physical attempt
observed:
  - OBSERVED all five attempts remained detached and the final failure had cup Z delta -0.0003559999999999952 m and lateral drift 0.0031041816957130606 m.
conclusion: TCP local +X is the wrong reseating direction for restoring the fixed-finger load path.
decision: REVERSE_SINGLE_VARIABLE
next_experiment: EXP-017
```

```yaml
experiment_id: EXP-017
status: INVALID
prior_experiment: EXP-016
hypothesis: The contact_direction_x sign describes the pad normal, so gripper reseating must move in local -X rather than +X.
prediction: The same bounded 0.2 mm local -X step restores fixed contact without q6 tightening or ceiling violation.
single_variable: Reverse reseating direction from local +X to local -X.
lifecycle: FULL_RESTART
preconditions:
  - Same five-attempt budget, q6, 0.2 mm magnitude, exact 2 mm micro-lift, and fail-closed ceiling.
success_criteria:
  - Strict physical gate passes and persists before attachment.
failure_criteria:
  - Fifth attempt fails or any strict assertion fails.
invalid_criteria:
  - Any other strategy/physics change, stale install, or duplicate runtime.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus authorized uncommitted strategy patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 171
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=171 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-18
    exit_code: 1 at DESCEND before reseating
observed:
  - OBSERVED DESCEND used an invalid 1-second waypoint mapping and failed at 0.013946 rad against 0.012 rad path tolerance.
conclusion: Reseating direction was not tested.
decision: RERUN_AFTER_RESTORING_PROVEN_DESCEND_TIMING
next_experiment: EXP-018
```

```yaml
experiment_id: EXP-018
status: INVALID
prior_experiment: EXP-016
hypothesis: Local -X bounded reseating restores fixed contact while preserving the penetration ceiling.
prediction: Same as EXP-017, with the previously proven 3-second DESCEND/LIFT timing restored.
single_variable: Reverse reseating direction relative to valid EXP-016; EXP-017 excluded.
lifecycle: FULL_RESTART
preconditions:
  - Proven DESCEND/LIFT/RETREAT timing restored; all other strict bounds unchanged.
success_criteria:
  - Strict physical gate passes before attachment.
failure_criteria:
  - Fifth attempt or any strict assertion fails.
invalid_criteria:
  - Failure before reseating due to unrelated environment/timing.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus authorized uncommitted strategy patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 172
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=172 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-19
    exit_code: 1 before motion
observed:
  - OBSERVED startup attachment state did not converge to detached before execute.
conclusion: Local -X reseating was not tested; runner lacked attachment/world readiness.
decision: RERUN_WITH_READINESS_GATE
next_experiment: EXP-019
```

```yaml
experiment_id: EXP-019
status: INVALID
prior_experiment: EXP-016
hypothesis: Local -X bounded reseating restores fixed contact while preserving the penetration ceiling.
prediction: Same as EXP-018 after proving detached attachment readiness before execute.
single_variable: Reverse reseating direction relative to valid EXP-016; invalid EXP-017/018 excluded.
lifecycle: FULL_RESTART
preconditions:
  - Runner proves controllers, MoveIt, and /so101/object_attached == detached.
success_criteria:
  - Strict physical gate passes before attachment.
failure_criteria:
  - Fifth attempt or any strict assertion fails.
invalid_criteria:
  - Failure before reseating due to unrelated startup state.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus authorized uncommitted strategy patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 173
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=173 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-20
    exit_code: terminated after read-only startup diagnosis
observed:
  - OBSERVED durable startup state was attached; a passive detached wait cannot converge.
conclusion: Local -X reseating was not tested.
decision: RESET_OWNED_WORLD_THEN_RERUN
next_experiment: EXP-020
```

```yaml
experiment_id: EXP-020
status: VALID
prior_experiment: EXP-016
hypothesis: Local -X bounded reseating restores fixed contact while preserving the penetration ceiling.
prediction: Same as EXP-019 after the owned runner explicitly resets startup attachment to detached and reads it back.
single_variable: Reverse reseating direction relative to valid EXP-016; invalid EXP-017/018/019 excluded.
lifecycle: FULL_RESTART
preconditions:
  - Runner discovers durable state, publishes owned detach reset, and proves detached before execute.
success_criteria:
  - Strict physical gate passes before attachment.
failure_criteria:
  - Fifth attempt or strict assertion fails.
invalid_criteria:
  - Startup/reset failure before physical strategy executes.
provenance:
  source_commit: 68b0fc6051eb57eb618d62bcaa21674594571d2a plus authorized uncommitted strategy patch
  install_overlay: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install
  ros_domain_id: 174
  gz_partition: assigned uniquely by run_pick_place_e2e.sh
commands:
  - command: ROS_DOMAIN_ID=174 bash test/headless/run_pick_place_e2e.sh /tmp/so101-py-g7LydYCB/task15-e2e-21
    exit_code: 0 from the known wrapper-status bug; installed live execute itself exited 1
observed:
  - OBSERVED the owned runner discovered the durable startup attachment, explicitly detached it, and read back detached before execution.
  - OBSERVED all five bounded attempts retained the initial seating q6 target and used cumulative 0.2 mm TCP-local -X reseating between attempts.
  - OBSERVED no attempt established the required six-sample bilateral stable contact boundary.
  - OBSERVED final evidence was fixed_finger=false, moving_jaw=false, with no measurable pad penetration; no physical-gate.json was created and no attach command was issued.
  - OBSERVED installed live execution exited 1 with `bilateral stability timeout: BilateralContactEvidence(fixed_finger=False, moving_jaw=False, max_fixed_pad_penetration_m=None, max_moving_pad_penetration_m=None, within_solver_depth_limit=False)`.
  - OBSERVED the runner cleaned its ROS_DOMAIN_ID=174 / Gazebo partition processes and tmux sessions.
conclusion: The authorized local -X reseating strategy also fails the immutable pre-attachment physical gate. Together with valid EXP-016 (+X failure), the bounded lateral-reseating design space approved for contact-missing retry is disproved without changing materials, q6 semantics, or physical assertions.
decision: STOP_AT_TASK_8_DESIGN_GATE
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-020
current_hypothesis: NONE; both authorized bounded TCP-local lateral reseating directions failed the real ROS/Gazebo pre-attachment gate.
working_tree_status: Task 15 recalibration/live implementation and experiment evidence remain uncommitted; no files are staged.
owned_processes: NONE after the isolated EXP-020 runner cleanup.
preserved_processes: codex and codex-cua tmux plus unrelated user processes; none were operated or interrupted.
confirmed_conclusions:
  - Main and Python cup/pad contact materials and world SDF remain byte-identical.
  - q6 retained the main-workspace seating target; the 2 mm world-Z micro-lift request and 0.000800002 m moving-pad ceiling were not relaxed.
  - Local +X reseating failed after five attempts (EXP-016); local -X reseating failed after five attempts (EXP-020).
  - EXP-015 achieved lift and lateral displacement but violated the immutable moving-pad ceiling, so it cannot satisfy the gate.
disproven_routes:
  - Bounded 0.2 mm TCP-local +X or -X reseating while holding q6 at the initial seating target.
  - Additional q6 squeezing within the tested path, because it exceeded the immutable moving-pad penetration ceiling.
open_risks:
  - Task 8 remains unproved; Tasks 9-16 runtime/GUI acceptance must not proceed through this failed hard gate.
  - The headless wrapper currently masks the installed live-execute nonzero status and must be fixed after a new physical design is approved.
minimal_design_decision_required: Approve a new physical recovery variable outside the exhausted lateral-reseat design (for example a bounded re-approach pose/orientation policy derived from observed contact geometry), while explicitly retaining materials, q6 lower-bound semantics, exact 2 mm micro-lift, and the 0.000800002 m moving-pad ceiling.
next_command: Await that minimal Task 8 physical-recovery design decision; do not start downstream runtime or GUI acceptance.
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-006
current_hypothesis: Aligning the stale seating endpoint, stabilizer order, and MoveIt world-Z request will recover the physical micro-lift.
working_tree_status: Task 15 live implementation and headless contract remain uncommitted; experiment ledger is untracked.
owned_processes: NONE; exact-PID cleanup completed for 2889118, 2917883, 2920823, 2926250, 2933521, 2939073.
preserved_processes: codex and codex-cua tmux; clang-tidy processes in unrelated worktrees.
confirmed_conclusions:
  - Main and Python world SDF/friction are identical; stale strategy/config is the first divergence (EXP-006).
disproven_routes:
  - Physics/material tuning is not justified before strategy alignment.
open_risks:
  - Python does not yet implement main's pose-constrained MoveGroup world-Z micro-lift request.
next_command: Write RED parity tests for the main@05dff7a seated endpoint, fixed preload target, and current-TCP world-Z request.
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: task15-e2e-7
current_hypothesis: Python sequence or assets differ from current main-workspace behavior.
working_tree_status: modified cli/pick_place_state_machine.py; untracked live_execute.py and three headless E2E files; untracked this ledger.
owned_processes: orphaned gz sim server PIDs 2889118, 2917883, 2920823, 2926250, 2933521, 2939073 from prior Python evidence runs; cleanup pending.
preserved_processes: codex and codex-cua tmux; clang-tidy processes in so101-workspace-sampler and so101-physical-outcome-validation.
confirmed_conclusions:
  - Pre-attach object micro-lift remains unproved and failed at 0.000003 m in task15-e2e-7.
disproven_routes:
  - Post-attach following is not acceptable proof; preload-only Python patch did not pass.
open_risks:
  - Six owned orphaned Gazebo server processes remain and must be terminated by exact PID before another stack.
next_command: exact-PID cleanup followed by read-only main-workspace comparison for EXP-006.
```

```yaml
checkpoint_id: CP-005-PHYSICAL-OUTCOME-MIGRATION
recorded_at: 2026-08-08 Asia/Shanghai
worktree: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py
branch: codex/so101-gazebo-demo-py
source_head: 68b0fc6051eb57eb618d62bcaa21674594571d2a
reference_only:
  semantic_head: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation@641f7c470bfea81934b0dc094afc42da4aaa5111
  runtime_dependency: FORBIDDEN
working_tree_status:
  tracked_dirty: motion/controller/object/validation policies, provenance, CLI, ROS-Gazebo backend, provenance test
  untracked_preserved: this ledger, live_execute.py, headless runner/assertion/contract, main-strategy parity test
  staged: NONE
owned_processes: NONE
preserved_processes: all unrelated Gazebo, clang-tidy, codex and codex-cua processes
approved_semantics:
  - physics-only cup motion from close through release; no normal forward Gazebo attachment
  - MoveIt attachment is collision-planning shadow from latest Gazebo pose
  - bounded intermediate telemetry plus unchanged hard gates
  - independent release settle epoch and strict final physical evaluator
  - Featherstone compound-owner intended-table support with calibrated bounded negative depth noise
  - unsupported held cup never auto-opens; final evidence precedes separate reset
migration_order: P1 domain/workflow -> P2 policy -> P3 observer/evidence -> P4 evaluator/settle -> P5 shadow-only runtime -> P6 recovery/consumers -> P7 parity -> P8 target calibration -> P9 acceptance
known_conflicts_in_preserved_task15:
  - live_execute TRACE/runtime still contain ATTACH_GAZEBO/DETACH_GAZEBO
  - forward runtime calls backend.set_attached and uses time.sleep for final settle
  - headless evidence expects Gazebo attached/detached events
  - wrapper status masking recorded by EXP-020
next_experiment: PY-PHYSICAL-P1-RED
next_command: add targeted Python domain/workflow/package-independence RED without first altering preserved Task 15 implementation
```

```yaml
checkpoint_id: CP-006-P1-GREEN
recorded_at: 2026-08-08 Asia/Shanghai
implementation_commit: 37689a3adc72df378de74a12333208103e8f91c1
experiment_id: PY-PHYSICAL-P1-RED
status: VALID
single_variable: Python domain/workflow forward-state ownership only
red:
  command: python3 -m pytest -q test/test_domain.py test/test_workflow.py test/test_package_independence.py
  observed: collection failed because State.WAIT_RELEASE_SETTLE did not exist
  note: initial worktree-root invocation was invalid due to source package import path and did not count
green:
  command: python3 -m pytest -q test/test_domain.py test/test_workflow.py test/test_package_independence.py
  result: 8 passed in 0.25s
implemented:
  - added WAIT_RELEASE_SETTLE and VALIDATE_FINAL_PLACEMENT
  - removed ATTACH_GAZEBO and DETACH_GAZEBO from Python State/forward graph
  - ATTACH_MOVEIT follows physical validation
  - DETACH_MOVEIT precedes OPEN_GRIPPER and release settle/final validation
preserved:
  - all pre-existing Task 15 tracked/untracked work remains unstaged
  - defensive RECOVER_DETACH_GAZEBO state remains
runtime_status: NOT_MIGRATED; live_execute/runtime/runner consumers still require P2-P6
owned_processes: NONE
next_experiment: PY-PHYSICAL-P2-RED
next_command: add strict physical_outcome policy parser RED tests; do not build or run ROS runtime
```

```yaml
checkpoint_id: CP-007-PHYSICAL-OUTCOME-PARITY-AND-TARGET-MATRIX
recorded_at: 2026-08-08 Asia/Shanghai
branch: codex/so101-gazebo-demo-py
implementation_head: 2b1787dd53c9f06b09c1b2997f9682e14f0e756e
implementation_commits:
  - 81dc512 strict physical-outcome policy
  - e004ddb timestamped support evidence
  - 743cba9 deterministic evaluator/release settle
  - 2ecbae9 runtime state registration
  - 505a690 non-resumable release epoch
  - 7b32bcb hold-first recovery
  - 1f5ebc5 physics-only live workflow and frozen 0.008 controller config
  - 2b1787d live plan-only and physical-grasp checkpoint
verification:
  command: fresh colcon build plus source overlay and full Python pytest
  result: 124 passed, 2 skipped
  package_prefix: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install/so101_gazebo_demo_py
preserved_dirty:
  - motion/object/validation targets and provenance from Task 15 remain uncommitted
  - so101_controllers.yaml 0.012 trajectory tolerance remains preserved but FORBIDDEN for valid runs
effective_safety_config: config/so101_controllers_physical_outcome.yaml with trajectory ceiling 0.008 rad
target_baseline:
  source: preserved Task 15 aligned to main@05dff7a; not yet qualified
  grasp_close_q6_rad: -0.047608632840292
  micro_lift_world_z_m: 0.002
  cup_radius_m: 0.040
  cup_height_m: 0.090
  rim_clearance_m: 0.008
  bottom_clearance_m: 0.020
  q6_safe_lower_rad: -0.059600220867817
search_order: A_TCP_TRANSLATION -> B_ORIENTATION -> C_Q6 -> D_MICRO_LIFT -> E_WAYPOINT -> F_TIMING
bounded_ranges:
  A: each axis independently within +/- approach_outside_clearance_m
  B: each component independently within existing state axis_tolerance_rad
  C: baseline through q6_safe_lower_rad only
  D: baseline 0.002 m through strictly below existing catastrophic drift ceiling
  E: existing joint limits and state validation envelope intersection
  F: pre-registered candidates not exceeding current policy scaling
runtime_status: NOT_RUN after parity migration
next_experiment: PY-PARITY-PLAN-001
next_command: preregister isolated all-state live plan-only with unique domain/partition/evidence root
```

```yaml
experiment_id: PY-PARITY-PLAN-001
status: PLANNED
purpose: Prove every configured motion waypoint ladder plans under the physical-outcome package before any target experiment.
single_variable: runtime parity only; no target value changes
lifecycle: FULL_RESTART
source_commit: a152bc532d80bee9162d4e24d478e19f778bd8cf
config_sha256:
  motion: 4ba7b35c315615a73238276ea511306bb98e2b4f30bddf0134f3183a6ef1ad4e
  object: da271bbba8a64eb9f6840227de67a6faecb4b224a7f3c9412eef65a9f5cc9dfe
  validation: f0153e5154a24b1beadfbb87067063843671b7bf6f1999abc77a5a06d9594ab2
  effective_controller: 7c4c2c5660cb13f2efbf2cfdbc224e20ec0e1c39d77d60f8d9fc62cd6e3ffdea
ros_domain_id: 191
gz_partition: so101_py_plan_191_20260808_a152bc5
evidence_root: /tmp/so101-py-plan-20260808-a152bc5-191
owned_tmux_session: so101-py-plan-191-a152
states: [MOVE_ABOVE_OBJECT, DESCEND, LIFT, MOVE_ABOVE_PLACE, DESCEND_TO_PLACE, RETREAT]
success_criteria:
  - package prefix is this worktree
  - generated SDF names so101_controllers_physical_outcome.yaml
  - every waypoint segment returns a nonempty MoveIt plan
  - no ExecuteTrajectory/controller goal and no Gazebo attachment command occurs
invalid_criteria:
  - startup/readiness/provenance failure before the first plan
cleanup_owner: only so101-py-plan-191-a152 and its recorded descendants
```

```yaml
experiment_id: PY-PARITY-PLAN-001
status: RUNNING
started_at: 2026-08-08 Asia/Shanghai
preflight:
  domain_partition_collision: NONE_OBSERVED
  preserved_ros_domain_181_stack: UNTOUCHED
  target_changes_after_registration: NONE
```

```yaml
experiment_id: PY-PARITY-PLAN-001
status: VALID_SUCCESS
completed_at: 2026-08-08 Asia/Shanghai
package_prefix: /data/work/ws_moveit/.worktrees/so101-gazebo-demo-py/install/so101_gazebo_demo_py
effective_controller_evidence:
  generated_sdf: /tmp/so101-py-plan-20260808-a152bc5-191/ros-logs/so101-prepared-90312.sdf
  config: config/so101_controllers_physical_outcome.yaml
  runtime_dump_trajectory_rad: 0.008 for joints 1-5
planned_points:
  MOVE_ABOVE_OBJECT: 199
  DESCEND: 125
  LIFT: 119
  MOVE_ABOVE_PLACE: 127
  DESCEND_TO_PLACE: 100
  RETREAT: 132
observed:
  - Every configured waypoint segment returned a nonempty plan; CLI returned PLAN_ONLY_COMPLETE for all six states.
  - Plan logs contain no workflow-issued ExecuteTrajectory, FollowJointTrajectory goal, attach, or detach command.
  - Startup durable attachment state was attached without a workflow command; this does not affect plan-only validity but requires defensive owned detach/readback before execute.
cleanup:
  tmux_session: removed
  detached_owned_gz_pid: 90360 terminated by exact PID after tmux cleanup left it orphaned
  partition_processes_remaining: NONE
  unrelated_domain_181_and_other_stacks: UNTOUCHED
conclusion: Python physical-outcome planning parity gate passed; target calibration may proceed to baseline short-path execution.
next_experiment: PY-A0-BASELINE-GRASP-001
```

```yaml
experiment_id: PY-A0-BASELINE-GRASP-001
status: PLANNED
purpose: Establish the first hard-gate failure of the preserved Python target baseline with exactly one physical attempt.
single_variable: NONE_BASELINE
lifecycle: FULL_RESTART
source_commit: c4fb2b88b976fb6d0744070d84d7276420558844
config_sha256:
  motion: 4ba7b35c315615a73238276ea511306bb98e2b4f30bddf0134f3183a6ef1ad4e
  object: da271bbba8a64eb9f6840227de67a6faecb4b224a7f3c9412eef65a9f5cc9dfe
  validation: f0153e5154a24b1beadfbb87067063843671b7bf6f1999abc77a5a06d9594ab2
  effective_controller: 7c4c2c5660cb13f2efbf2cfdbc224e20ec0e1c39d77d60f8d9fc62cd6e3ffdea
ros_domain_id: 192
gz_partition: so101_py_a0_baseline_001_192
evidence_root: /tmp/so101-py-a0-baseline-001-192
owned_tmux_session: so101-py-a0-192
command_boundary: execute --stop-after VERIFY_PHYSICAL_GRASP
attempt_count: 1
success_criteria:
  - startup owned reset proves Gazebo detached
  - bilateral contact is stable for the configured consecutive evidence samples
  - moving-pad penetration <= 0.000800002 m
  - 2 mm world-Z micro-lift and existing lateral bound pass
failure_criteria:
  - any existing controller/collision/penetration/physical-grasp hard gate fails
invalid_criteria:
  - startup, provenance, bridge, controller, MoveIt, or pose/contact observation fails before target behavior is exercised
post_failure: stop/hold; preserve evidence; no automatic open or reset before capture
```

```yaml
experiment_id: PY-A0-BASELINE-GRASP-001
status: RUNNING
started_at: 2026-08-08 Asia/Shanghai
preflight:
  domain_partition_collision: NONE_OBSERVED
  all_waypoint_plan_only: PASSED_BY_PY-PARITY-PLAN-001
  candidate_retry_count: 0
```

```yaml
experiment_id: PY-A0-BASELINE-GRASP-001
status: INVALID
completed_at: 2026-08-08 Asia/Shanghai
target_behavior_exercised: false
command_boundary: before MOVE_ABOVE_OBJECT
observed:
  - "CLI failed closed before motion: fresh Gazebo/TCP pose pair unavailable; object and TCP were both None in the workflow sample."
  - "Root cause: /so101/gazebo_pose_info discards Gazebo entity names, while so101_tcp is a composite TF frame and is not published as a standalone dynamic /tf transform."
  - "Read-only diagnosis after fix 7df97ec resolved plastic_cup directly from Gazebo Pose_V and world->so101_tcp through tf2; observed pose_pair_age_s was 0.073 s against the unchanged 0.1 s freshness gate."
evidence:
  directory: /tmp/so101-py-a0-baseline-001-192
  observer_fix_commit: 7df97ec24333a467822f59ed96942f92de4b6803
cleanup:
  tmux_session: removed
  detached_owned_gz_pid: 99290 terminated by exact PID after tmux cleanup left it orphaned
  ros_domain_192_daemon: stopped
  unrelated_tmux_and_ros_stacks: untouched
candidate_result: EXCLUDED
hard_gate_result: NOT_EVALUATED
decision: TERMINATE_BATCH_AND_FULL_RESTART_WITH_NEW_EXPERIMENT_ID
next_experiment: PY-A0-BASELINE-GRASP-002
```

```yaml
experiment_id: PY-A0-BASELINE-GRASP-002
status: PLANNED
purpose: Exercise the unchanged Python target baseline once after repairing authoritative live pose observation.
single_variable: NONE_BASELINE
lifecycle: FULL_RESTART
source_commit: 772e2be665da0cd6a21349d41cadee8284de691e
config_sha256:
  motion: 4ba7b35c315615a73238276ea511306bb98e2b4f30bddf0134f3183a6ef1ad4e
  object: da271bbba8a64eb9f6840227de67a6faecb4b224a7f3c9412eef65a9f5cc9dfe
  validation: f0153e5154a24b1beadfbb87067063843671b7bf6f1999abc77a5a06d9594ab2
  effective_controller: 7c4c2c5660cb13f2efbf2cfdbc224e20ec0e1c39d77d60f8d9fc62cd6e3ffdea
ros_domain_id: 193
gz_partition: so101_py_a0_baseline_002_193
evidence_root: /tmp/so101-py-a0-baseline-002-193
owned_tmux_session: so101-py-a0-193
command_boundary: execute --stop-after VERIFY_PHYSICAL_GRASP
attempt_count: 1
preconditions:
  - fresh single-package build and package test suite passed with 127 passed and 2 skipped
  - package prefix is this worktree
  - domain 193 and partition have no observed process collision
  - defensive Gazebo detach and detached readback complete before execute
success_criteria:
  - bilateral contact is stable for the configured consecutive evidence samples
  - moving-pad penetration <= 0.000800002 m
  - 2 mm world-Z micro-lift and existing lateral bound pass
failure_criteria:
  - any existing controller/collision/penetration/physical-grasp hard gate fails
invalid_criteria:
  - startup, provenance, bridge, controller, MoveIt, or pose/contact observation fails before target behavior is exercised
post_failure: stop/hold; preserve evidence; no automatic open or reset before capture
```

```yaml
experiment_id: PY-A0-BASELINE-GRASP-002
status: INVALID
completed_at: 2026-08-08 Asia/Shanghai
target_behavior_exercised: false
command_boundary: launch overlay setup
observed:
  - Both owned tmux windows exited before launching ROS nodes with package so101_gazebo_demo_py not found.
  - The tmux default zsh sourced setup.bash without an explicit bash -lc boundary; a read-only bash -lc probe resolved the correct worktree package prefix.
evidence:
  directory: /tmp/so101-py-a0-baseline-002-193
  gazebo_log: gazebo.log
  moveit_log: moveit.log
cleanup:
  tmux_session: exited without surviving session
  ros_domain_193_daemon: stopped
  partition_processes_remaining: NONE
  unrelated_tmux_and_ros_stacks: untouched
candidate_result: EXCLUDED
hard_gate_result: NOT_EVALUATED
decision: TERMINATE_BATCH_AND_FULL_RESTART_WITH_EXPLICIT_BASH_LC
next_experiment: PY-A0-BASELINE-GRASP-003
```
