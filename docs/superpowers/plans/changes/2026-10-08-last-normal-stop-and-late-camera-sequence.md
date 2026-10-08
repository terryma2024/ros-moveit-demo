# Data-side defects behind the window and scene-read fixes (normal stops, final boundary, reference check, sequence, speed)

Date: 2026-10-08

Trigger: the stops met on the pilot bag `031b82c6` once the capture ran to the end of the episode. Each is a defect of the data side that no earlier run reached.

## 1. The Teacher publishes three `normal_stop` events; the Recorder takes exactly one

- Evidence: `_normal_stop_proof` publishes a `normal_stop` event for every confirmed stop: the release preflight (seq 36, 104.872 s), the gripper-open proof (seq 41, 105.020 s) and, with a Recorder, the final proof after the sequence (seq 58, 115.298 s). `RecorderDataSide._data_retain_normal_stop` accepts one and raises `TEACHER_NORMAL_STOP_REPEATED` on the second; no live run that reached the release could be VALID.
- Options: (a) the Teacher publishes `normal_stop` only for the final proof; (b) the Recorder takes the last one.
- Recommended option taken (CP-3394, CP-3440): the Recorder's rule stays strict (exactly one boundary). The offline processor sees the whole recorded bag, so it marks the stops that are not the last before `terminal` (`final_normal_stop_seq` in the scan): they are audited as Teacher events and are not the boundary. For live runs, (a) is the contract to implement in the Teacher (one removed `_publish_teacher_event` call for the two release-time proofs); that is a Teacher change and is not made here.

## 2. The normal stop must end the capture when it arrives

- Evidence: `capture.on_normal_motion_end` was applied only in the tail, after `terminal`. The Teacher takes its end observation and publishes `terminal` 0.5 s after its final stop on the pilot bag, so the capture minted and labelled rows through those 0.5 s and then `CAPTURE_LABEL_REVOKED`.
- Rule (`ros/recorder_data_side.py`): `_apply_normal_stop` (boundary in the audit, capture told, `_collection_normal_end_clock` set) runs when the stop is retained, if the capture has its initial capture and a first command; the tail applies it only if that did not happen. Rows after the stop are not requested.
- Test: `test_the_normal_stop_ends_the_capture_when_it_arrives_not_at_the_tail`.

## 3. The final boundary must be searched when the stop is known (offline processor)

- Evidence: `_finish_native_collection` (first world record after the stop, at most 100 ms of simulation time later; camera tail) ran after `terminal`, 0.5 s after the stop: `ENDPOINT_CAPTURE_CLOCK_INVALID`. The offline processor starts it when the final stop is processed (`OfflineRosSources.on_teacher_event`); the live Recorder needs the same (start the final boundary at the stop, not at the terminal), or a Teacher that publishes `terminal` at once.

## 4. The reference check before the seal read only the last 8.2 s of raw samples

- Evidence: `RosRecorderSources.physics_steps` returned the physics adapter's history (4096 samples, 8.2 s); the Teacher's start observation, 90 s earlier, was never in it: `TEACHER_REFERENCE_PHYSICS_STEP_ABSENT` on every long episode. The audit holds every chunk and the post-seal readback already reads it.
- Rule: `physics_steps` returns the raw samples of the audit's `physics_chunk_v1` events (adapter history as the fallback). Test: `test_the_reference_check_reads_every_raw_sample_of_the_episode_not_only_the_adapters_last_8_seconds`.

## 5. A camera's retained acquisition sequence need not start at 1

- Evidence: the adapter numbers every frame; only frames from the capture start are audited. With the window after the worker's pause the first audited head frame is sequence 2 and the seal failed `AUDIT_ACQUISITION_INVALID`.
- Rule (`act/episode_audit.py::_verify_streams`): the first audited sequence of a camera may be any positive integer; each next one must be exactly +1 with a later stamp. A gap inside the retained sequence is still refused. Tests in `test_act_episode_audit.py`.

## 6. The camera-tail wait used an attribute that does not exist

`_finish_native_collection` took `capture._lock`; the capture's lock is `ingress_lock`. The wait was never reached before, and the unit-test fake had the same wrong name. Fixed in both (RED first).

## 7. The seal and the QC were quadratic in the episode length

`verify_world_source` hashed the whole model once per world source (about 8000 per 100 s) and scanned the raw samples once per source in the QC. The model hash is memoised on the model object, and a long raw-sample list is indexed once (temporaries, such as the seal's one-element lists, are scanned and never cached). A 100 s episode took more than 30 minutes to seal before. Test: `test_the_raw_step_index_matches_the_scan_it_replaces_and_follows_the_list_it_is_given`.

## 8. Replay: only the world evidence is withheld before the window

Withholding every source before the window start dropped the physics chunk of the first world record (it arrives just before that record): `WORLD_SOURCE_NATIVE_REQUIRED`. Only `/so101/simulation/evidence` is withheld (`replay.py`). Waiting loops of the data side advance the virtual clock by 2 ms per pass (`OfflineRosSources.PROGRESS_STEP_S`), as a live pass costs real time.

## 9. The QC report could not validate a PASS (physics count 0), and its NaN-tagged records could not be decoded

- `recompute_native_qc` counted `physics.jsonl` rows for `counts.physics`; nothing has written that stream since the Recorder was decoupled, so the count was 0 and `validate_qc_report` (a PASS needs every count above 0) refused the QC's own PASS (`QC_REPORT_INVALID: verdict`). `counts.physics` is now the number of retained raw `physics_chunk_v1` events (`physics_chunk_count`).
- `scene_association.decode_ros` could not decode a retained record that carries the audit's `__non_finite_float__` tags (a planning-scene read with NaN fields): `SOURCE_ALIGNMENT_ROS_CONTENT_INVALID`. It restores the tags first and compares the re-encoded message with the tagged record; finite records are unchanged. Test: `test_a_retained_ros_record_with_tagged_non_finite_values_decodes_and_round_trips`.
- The world observer's records after the final capture are no longer retained (`_drain_world_sources`), because their raw sample follows up to 100 ms later and the seal needs it (`WORLD_SOURCE_NATIVE_REQUIRED`).

Contract impact: 5 widens what the audit accepts as described; 2 to 4, 6 and 7 are defects fixed with no rule changed; 1 and 3 are decisions for the live path (Teacher publishes only the final stop; final boundary at the stop).

Rollback: `writer-artifacts/p2-normalstop-base.tar.gz`, `p2-perf-base.tar.gz`, `p2-roundA-base.tar.gz`.

Ledger CP: CP-3440.
