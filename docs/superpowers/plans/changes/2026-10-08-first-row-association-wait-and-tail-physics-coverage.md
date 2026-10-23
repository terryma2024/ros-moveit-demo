# First-row association wait and tail wait for the end observation's physics chunk

Date: 2026-10-08

Trigger: production run of the offline processor on pilot bag 8d9ed9d3 (no diagnostic flag). Two flow races of the Recorder's sources, both visible only on a replay that is faster than the live loop. Neither relaxes a rule; both make a row or the tail wait for evidence that is certain to arrive.

## 1. A row waits for an association job that is issued and not built yet

- Evidence: the first row (21.9 s) failed `LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID`. The Teacher's SETUP apply (21.862 s) and read-back (21.884 s) had been ingested, so the tracker no longer listed the apply as owed, but the association job was built on the next pass. Until then nothing was owed or pending and `SceneAssociations.at()` returned the older `initial` association (21.664 s), whose geometry has the cup at its nominal pose; the planning-scene read at 21.864 s carries the settled pose.
- Rule: `SceneAssociations.at(at_s, tracker, unbuilt_sim_times)` returns `None` (the row waits) while a job whose anchor is at or before `at_s` is issued and not admitted. `RosRecorderSources._unbuilt_job_sim_times()` lists the anchors of `_jobs`. Rows still never guess.
- Tests: `test_p2_association_jobs_owed.py` (2 tests; the keyword did not exist before).

## 2. The tail waits until the end observation's physics step is retained

- Evidence: after the first two fixes and with the controller_state faults of the bag removed in a scratch copy, the run ended `TEACHER_REFERENCE_END_AFTER_RECORDING`. The Teacher's end observation is step 56421 (115.770 s), inside raw chunk 56401-56450, which ends at 115.828 s and reaches the bag after `terminal`. The camera grid (collection end 115.8 s) reached the observation first, `tail_ready` was true at once, and the newest retained step was 56400. The raw chunk grid and the camera grid have different phases, so this happens whenever the next camera instant after the observation lies before the end of its chunk (about 28 % of runs; it never showed with bag 031b because its grid phase put the camera instant after the chunk end).
- Rule: `RosRecorderSources.tail_ready` additionally requires `physics_adapter.retained_step_range()[1] >= end observation step` (the bounded wait and `RECORDER_TAIL_NOT_REACHED` of the engine are unchanged). An adapter without the accessor, or an observation without a step, behaves as before.
- Tests: `test_p2_tail_physics_coverage.py` (3 tests; the first was RED).

Contract impact: none. The reference check, the window rules and the QC are unchanged; the tail now waits for the sample the check already requires.

Rollback: `writer-artifacts/p2-assocjobs-base.tar.gz` (recorder_scene.py, episode_recorder_sources.py before item 1) and `writer-artifacts/p2c-tailphys-base.tar.gz` (episode_recorder_sources.py before item 2); sha256 files beside them.

Ledger CP: not recorded (the ledger is the main agent's).
