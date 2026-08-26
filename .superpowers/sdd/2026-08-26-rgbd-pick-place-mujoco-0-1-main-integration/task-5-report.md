# Task 5 Linux report

## Status

`REPAIRED_FIVE_RUN_BATCH_VALID_FINAL_REVIEW_APPROVED`

The immutable repaired runtime implementation is
`3ea1530530b274af3b3db5b9aa50165ae66b7e31`, with formal child main
`5e9d67ce9fde39d35bf94cc498721abf203a0ddd`; installed fork, support, teleop,
and demo packages report `0.1.0`. Canonical `/data/work/ws_moveit` remained read-only and was never
sourced, built, fetched, checked out, pulled, cleaned, or modified.

EXP-048 remains the old-policy RED: a 2 mm TCP micro-lift produced only 0.735331 mm physical cup lift
at the forward keyframe, below the unchanged 1 mm gate. TDD changed only the MuJoCo micro-lift target
to 4 mm and added fresh failure-state terminal joint generation/stamp, joint, FK-TCP/error, and
cup/contact evidence persisted before raise. The 1–10 mm physical gate, perception route, grasp,
other targets, speed, physics, and physical truth are unchanged. A review-requested second RED/GREEN
round prevents cached terminal JointState evidence by waiting past each execution boundary.

## Static verification

- Focused review tests: 2 passed; dynamic execute module: 10 passed.
- Complete installed `so101_demo_py`: 448 passed.
- `so101_mujoco_support`: 19 passed; all 24 `so101_teleop` CTest targets pass.
- Fork: 352 tests, zero errors/failures, 16 documented platform/configuration skips.
- All project packages and six fork packages rebuilt successfully in isolated installs.
- Installed policy SHA256: `7d36a45b9382ba2d8a8d16646e66539ee8f1e499633f7a1b5c266d5ffbfded70`.

## Five independent FULL_RESTART results

| Experiment | Keyframe | Perception error | Physical micro-lift | Max terminal TCP error | Final XY error |
|---|---|---:|---:|---:|---:|
| EXP-052 | task_start | 0.642 mm | 2.694 mm | 0.716 mm | 2.336 mm |
| EXP-053 | forward 5 cm | 0.594 mm | 3.171 mm | 1.292 mm | 1.729 mm |
| EXP-054 | left 5 cm | 0.693 mm | 2.843 mm | 0.854 mm | 1.966 mm |
| EXP-055 | right 5 cm | 0.631 mm | 3.666 mm | 1.575 mm | 2.403 mm |
| EXP-056 | task_start repeat | 0.642 mm | 2.711 mm | 0.742 mm | 2.391 mm |

Every runner and GUI watcher exits zero. Each production chain uses MuJoCo RGB-D, retained point
cloud, tf2, source-stamped world `/cup_pose`, dynamic workflow, MoveIt, controller, and MuJoCo
physical feedback, then reaches `DONE` with 19 transitions. Every run proves nonzero trajectory and
fresh monotonic terminal joint/TCP evidence, bilateral unsupported grasp/lift/transport, MoveIt
attach, detach-before-open, stable table-supported release, zero final fingertip contacts, world sync,
and retreat. The forward-keyframe physical lift is 3.170878 mm versus EXP-048's 0.735331 mm, with the
1 mm lower gate unchanged.

Fifteen fresh exact-window images were inspected: the proper initial cup offset, visibly elevated
held transport, and upright final cup inside the red ring with the gripper open appear in each run.
Each three-stage set preserves one exact Viewer window ID/PID. All five stacks emit ordered MoveIt
and controller shutdown markers; direct no-daemon domain reads, exact process scans, target tmux
checks, and Viewer inventories are empty afterward. Unrelated sessions remain untouched.

No truth bridge/publisher, fixed workflow, perception bypass, direct object write, simulator
constraint, physics edit, or reduced threshold was used.

## Evidence disposition

- Retained primary: all repair RED/GREEN/build/test/provenance evidence, EXP-048 root cause, and
  EXP-052 through EXP-056 perception/dynamic/GUI/cleanup artifacts under the sole Linux evidence root.
- Retained historical/non-counting: EXP-027, EXP-032, EXP-037, EXP-042, and EXP-047.
- Archived: none.
- Deletion candidates only: superseded non-qualification `gui-watcher-smoke`, `build-discovery`, and
  generated `log`/`project-log` after an owner-approved retention window. No experiment, root-cause,
  provenance, test, install, or qualification artifact is a deletion candidate.

Final fresh review independently inspected the implementation, tests, provenance, five raw evidence
sets, and all 15 PNGs and returned `FINAL_APPROVED_TO_PUBLISH` with no correctness, provenance,
evidence, schema, or report blocker. It noted only a non-blocking transient startup exact-stamp TF
race in EXP-055/056; the same production perception path subsequently produced its source-stamped
`OK` sample in both runs.

The Mac orchestrator should use implementation commit `3ea1530` for its fresh four-position
regression after this Linux closure commit is pushed.
