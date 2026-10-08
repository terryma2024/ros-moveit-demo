# Cleanup step 2: the live Recorder is removed

Date: 2026-10-08

Trigger: the amendment (section 7) deferred the removal of the live Recorder's machinery until the run path had been verified on real data. The switch (P3) is committed and the L1 to L7 freeze passed, so the user approved step 2 of the cleanup inventory (`p3-cleanup-inventory-curated.tsv`).

Options considered:

1. Keep the live modules and only stop importing them (step 1). Rejected for step 2: about 3,300 lines of threads, spool processes, a ready-file protocol and a fault injector that nothing runs, and two engines to keep in agreement.
2. Delete in place and let the processor's subclasses lose their base classes. Rejected: the processor subclassed `RecorderEngine` and `RosRecorderSources`; deleting the bases would break it.
3. Move what the processor needs into `act/offline/`, then delete the originals. Taken.

Recommended option taken under CP-3394: option 3. The work is proved by a golden comparison taken before the first edit (below).

## What changed

New in `act/offline/`:

- `engine.py`: `OfflineEngine`, one class in place of `RecorderEngine` plus the processor's subclass. It keeps the event inbox and monitor, the verdict latch, `process(node, preset_reasons)`, `finalize`, the tail wait, the source check, the seal and the readback, the inventory and the result document. It drops the ready file (LISTENING and CAPTURING), `run()` and `should_stop`, the stall telemetry and process discipline, the fault injector hooks and the deferred events.
- `sources.py`: `OfflineRosSources`, one class in place of `RosRecorderSources` plus the processor's subclass. It keeps `ControllerReferencePort` (and `controller_state_qos`), the source binding, the provider, the association logic, the bracket rules, `try_start`, `collect`, `tail_ready`, the final-boundary search that starts at the final `normal_stop`, and the replayed scene reads.
- `policy.py`: `load_recorder_policy`, `RecorderConfigRefused`, `POLICY_KIND` and the closed field set, moved unchanged.

Deleted whole (lines before the change):

| File | Lines |
| --- | --- |
| `cli/act_episode_recorder.py` and its `setup.py` entry | 150 |
| `ros/recorder_receiver.py` | 95 |
| `act/chunk_spool.py` | 286 |
| `act/controller_spool.py` | 348 |
| `act/spool_lifecycle.py` | 41 |
| `act/recorder_telemetry.py` | 248 |
| `act/episode_recorder_process.py` | 957 |
| `ros/episode_recorder_sources.py` | 1,216 |
| Total | 3,341 |

Removed from files that stay:

- `act/collection_orchestration.py`: `RecorderOrchestrator`, `RecorderLaunch`, `RECORDER_ROLE`, `RECORDER_PROCESS_FAULTS` and the helper `_read_json`. `CollectionOptions`, `validate_collection_request`, `collection_from_document`, `require_under_sandbox`, `RecorderOutcome` and `CollectionRefused` stay. `FAULT_SANDBOX_COMPONENT` is now defined here; `COLLECTION_FAULTS` is the same six values.
- `adapters/act/ros_episode_physics.py`: the dedicated receiver thread and private node, the spool reader, `accept_record` and its helpers, the backlog bound (`_note_backlog`, `spool_backlog_max_frames`) and `earliest_sample_time_s`. `accept_message`, `drain`, the lookups, `receipt_diagnostics` and the receiver-lag check (`_check_lag`, `end_lag_check`) stay: the lag check is a live rule on the replay too.
- `ros/data_source_binding.py`: the real-node and spool branches, `spool_stats` and the `physics_backlog_max` argument.
- `act/offline/replay.py`: `ReplayReceiver`.
- Comments that named the live process (`episode_open.py`, `dynamic_cup_pick_place.py`, `dynamic_runtime.py`, `parallel_worker_runtime.py`) were reworded.

Kept on purpose:

- `config/act/episode_recorder_v1.yaml` and its closed schema, including keys only the live Recorder read (`ready_timeout_s`, `capturing_timeout_s`, `exit_wait_s`, `term_grace_s`, `physics_spool_backlog_frames_max`). The policy is baked into every frozen inputs manifest and the golden replays use old manifests, so the schema and the file bytes cannot change. Nothing reads those keys now. `parallel_collection_v3.yaml` stays for the same reason.
- `ros/recorder_data_side.py` and its diagnostics: reused rule code.

## Behaviour that is not byte-for-byte the old behaviour

1. **No deferred Teacher events.** A Teacher event other than `scene_operation` that arrives before the capture started used to be held and replayed at the start. It is now counted, not retained, and the data is INVALID at the finish with `RECORDER_NOT_READY_BEFORE_TEACHER_EVENT` (the same reason and facts as before for a capture that never started, plus `capture_started` as it stands). The result field `deferred_replayed` is the constant 0; `deferred_first` still names the first early event. All eight golden runs had zero held events, and the replay starts the capture before the Teacher's setup scene.
2. **Result document constants.** `SO101_RECORDER_RESULT_V1` keeps its shape. `fault`, `faults`, `listening`, `stall_telemetry`, `pid` and `deferred_replayed` are constants (`"none"`, zero counters, `true`, `{}`, `0`, `0`).
3. **`physics-source-failure.json`** (written only for an INVALID physics source): `receipt_diagnostics` no longer has `max_spool_backlog_frames` (it was always 0 offline).
4. `sources_factory` of `process_bag` (a test seam) no longer receives a fault injector.

## Golden comparison (taken before the first edit)

Evidence: `handoffs/teacher-act-decoupling-20261005.1RmsJ3ZJ/writer-artifacts/golden-20261008/` (inputs, run scripts, hashes, `compare-outputs.py`, `timings.txt`). The production processor was run with the real-run invocation on:

- bag 147cb073 (1,727 output files), twice before the change and once after (`run1`, `run2`; `run4`; `run3` was an intermediate state of the source and is not used);
- the L2 bag of 45315499 (1,713 files), twice before and once after;
- six INVALID cases once before and once after: 429dbf50 (`LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID`), 8d9ed9d3 (`OFFLINE_SOURCE_GAP`, arm), 031b82c6 (`OFFLINE_CAMERA_GRID`), and the fault bags `source_gap`, `queue_overflow` and `late`.

"Byte-identical" has to be defined, because two runs of the same code on the same bag already differ. The measured nondeterminism of the committed code (run 1 against run 2) is exactly:

| Id | What | How it is compared |
| --- | --- | --- |
| N1 | random UUID4 ids of the scene-association code (about 880 per bag) | up to a consistent renaming |
| N2 | `queue_evidence.events[].monotonic_s` in `audit/events.jsonl` (wall-clock stamps of the lossless writer queue) | dropped |
| N3 | digests of N1/N2 content: `audit-manifest.json`, `seal.json`, `qc-report.json`, the QC memo (`fingerprint`, `report_sha256`), and their copies in the processor report and the result | blanked by exact path, must still be 64-hex |
| N3b | the `episode_inventory` digests of `audit/events.jsonl` and `records.jsonl` in an INVALID result | blanked by exact path |
| N4 | the QC staging file name `.qc-report.json.<32 hex>.pending` | ignored |
| N5 | report `timing`, result `elapsed_s` and `pid` | dropped |
| N6 | the memo's `code_digest` (it covers the source, so it changes with this very change) | blanked |
| N7 | CDR alignment padding bytes of the rejected chunk in `physics-source-failure.json` (three runs gave three byte strings; the decoded messages are equal) | length only |
| N8 | the removed key `max_spool_backlog_frames` | dropped |

Result: for both real bags and all six INVALID cases the comparator reports EQUIVALENT between the run before and the run after the change. For the two real bags 1,719 of 1,728 and 1,705 of 1,714 files are byte-identical by sha256; the remaining eight per bag are exactly the files N1 to N3 name, plus the staging file. Every frame, acquisition, reference, row binding, input, physics file, `episode.json` and `source.json` is byte-identical. The comparator was validated first: run 1 against run 2 is EQUIVALENT, and 147cb073 against 45315499 is NOT_EQUIVALENT.

The earlier statement that the P2 production processing is deterministic was not true at byte level; the list above is the corrected definition.

## Verification

- Gate (`pytest -n 8`, cwd outside the worktree, the three git-cwd provenance files excluded): 7,467 passed, 186 skipped, 0 failed (before: 7,605 passed, 186 skipped; the net 138 fewer tests are the removed live-only tests below, minus the replacements).
- Scratch colcon install (fresh build and install bases): build OK; run from the installed package with cwd outside the worktree: `test_package_identity`, the P3 detector-pin and role-provenance tests, `test_p3_rework`, `test_p3_offline_switch`, `test_p2_offline_processor`, `test_act_episode_recorder`, `test_act_child_recorder_binding`, `test_act_collection_orchestration` and `test_act_data_path_isolation`: 254 passed. `test_installed_provenance` needs a git cwd (it is one of the three files the gate excludes) and was not run; the installed `lib/so101_demo_py/` has `act_offline_episode` and no `act_episode_recorder`, and no removed module is in the installed tree.
- Line counts of `.py` files: source 156,213 to 153,781 (-2,432; 487 to 481 files), tests 133,828 to 131,410 (-2,418; 459 to 451 files).
- No symbol left over: `rg` finds no use of `episode_recorder_process`, `episode_recorder_sources`, `recorder_receiver`, `chunk_spool`, `controller_spool`, `spool_lifecycle`, `recorder_telemetry`, `RecorderOrchestrator`, `RecorderLaunch`, `RosRecorderSources`, `RecorderEngine`, `FaultInjector`, `make_recorder_node`, `spin_burst` (of the Recorder; the Teacher's own `_spin_burst` is a different function), `NodeReceiver`, `SpoolProcess`, `accept_record` or `act_episode_recorder` (the console script) in source, tests, setup or config. A scan of every function and class of the touched modules for names without a use found one orphan (`earliest_sample_time_s`), which was removed.

## Tests

Whole files deleted (52 test functions): `test_rec2_receiver`, `test_rec_chunk_spool`, `test_rec3_controller_spool`, `test_rec3_spool_lifecycle`, `test_rec5_spool_convert`, `test_rec2_telemetry`, `test_rec8_deferred_events`, `test_c5_recorder_spin`. Reasons and replacements: `p5-cleanup-tests-removed.tsv`.

Tests removed or added inside files that stay (68 removed, 22 added): `p5-cleanup-tests-changed.tsv`, one row per test with its reason or replacement. The helpers other tests share (`build`, `teacher_script`, `SyntheticSources`, `make_episode`, `readback`) moved with their file, `test_act_episode_recorder.py`, which now drives `OfflineEngine.process`. The imports of about thirty other test files were retargeted (`OfflineRosSources`, `act.offline.policy`, `act.offline.engine`).

## Rollback

`p5-base.tar.gz` (sha256 in `p5-base.tar.gz.sha256`) holds every file this change touched or deleted as of the parent commit.
