# The ACT stack's move_group does not publish `/monitored_planning_scene`

Date: 2026-10-08

Trigger: in pilot bag 8d9ed9d3 the planning-scene reads carry the attached cup's colour until 61.618 s and not from 61.668 s (031b: 61.578 / 61.682 s), until the detach. The attach association (made at 61.400 s) then no longer matches the scene and the row audit fails `LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID` for the rest of the episode.

## 1. The earlier explanation was wrong

`2026-10-08-teacher-event-clocks-colour-and-single-final-stop` item 2 blamed the ACM-only apply. The bag disagrees: the reads at 61.518, 61.570 and 61.618 s, after the ACM apply (61.496 s), still carry the colour, and the Teacher's apply already had `robot_state.is_diff = True`. In the new bag the colour disappears about 250 ms after the attach, the period of the planning-scene publishing thread (4 Hz).

## 2. Reproduction (`so101_mujoco_support/test/test_planning_scene_colour_after_acm_apply.cpp`)

MoveIt's own `PlanningSceneMonitor` is fed the Teacher's three recorded apply requests (fixtures: SETUP, attach, ACM-only apply, taken from the bag):

- `PlanningScene` alone, or a monitor that does not publish, with joint states arriving: the colour of `plastic_cup` stays through all three requests (`AMonitorThatDoesNotPublishKeepsTheAttachedCupColour`, `TheAttachedCupKeepsItsColourThroughTheTeachersAcmOnlyApply`, 5 of 5 runs).
- A monitor that publishes `/monitored_planning_scene` (move_group with `publish_planning_scene` true): the colour is gone one publishing period after the attach, 5 of 5 runs (`DISABLED_APublishingMonitorLosesTheAttachedCupColour`, run with `--gtest_also_run_disabled_tests`; evidence `writer-artifacts/p2c-moveit-evidence.out`). Re-asserting `object_colors` in the ACM apply does not help: the colour is lost again at the next publish.
- The mechanism (MoveIt, not ours to patch): a publishing monitor keeps its scene as a diff of a parent scene; the publishing thread pushes the diff to the parent and clears it, and the colour of an object that is attached (not in the world) is dropped on the way.

## 3. Change

Correction (pilot 429dbf50, CP-3449): the launch flags alone were not enough. `MoveItCpp` starts publishing the maintained planning scene whatever `publish_planning_scene` says (the move_group log of that run still read "Publishing maintained planning scene on 'monitored_planning_scene'" with the flag false) and the colour was lost again from 63.07 s. The fix is in `graceful_shutdown_move_group`: when the launch has `publish_planning_scene` off it calls `stopPublishingPlanningScene()` right after `MoveGroupExe` is built. The C++ test `AMonitorWhosePublishingWasStoppedAgainKeepsTheAttachedCupColour` models exactly that (publishing started, then stopped, then the Teacher's three requests: the colour stays, 3 of 3). The launch flags stay: they say what the stack wants, the executable enforces it.

`launch_composition._moveit_parameters(..., publish_planning_scene=...)`; the stack built for the ACT profile passes `False`, which turns off `publish_planning_scene`, `publish_geometry_updates`, `publish_state_updates` and `publish_transforms_updates` of move_group. Nothing in the ACT stack reads `/monitored_planning_scene` (only the RViz configurations do, and the other stacks keep publishing). The Teacher's messages are unchanged (the `is_diff` line of the ACM apply is harmless and stays).

Tests: `test_p2_moveit_scene_publishing.py` (3 tests) and the C++ test above.

Contract impact: none. The scene content the Recorder compares is the same; MoveIt no longer loses part of it.

Rollback: `writer-artifacts/p2c-launch-base.tar.gz` (`launch_composition.py`), `p2c-support-base.tar.gz` (`so101_mujoco_support`), `p2d-applybracket-base.tar.gz` (`graceful_shutdown_move_group.cpp` before the stop call); sha256 beside them.

Ledger CP: CP-3445.
