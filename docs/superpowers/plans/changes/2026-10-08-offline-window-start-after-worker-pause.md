# Offline episode window starts after the worker's last pre-Teacher pause

Date: 2026-10-08

Trigger: pilot bag `031b82c6`. The worker freezes the simulation for the inference snapshot after it has started the Recorder (and the raw pilot): `point_initial_gate` runs `_start_recorder_first`, `_start_execute_consumer`, then `_pause_physics`. The world topic published one `paused=True` record (step 9274, sim 21.730 s) for that pause, 2.8 s before the Teacher's `reset_complete` payload (24.574 s). `native_endpoints.validate_world_source` refuses a paused record (`WORLD_SOURCE_SCOPE_INVALID`), the next record's `publisher_sequence` is then not previous + 1 (`WORLD_SOURCE_SEQUENCE_INVALID` on every later record), the Teacher's SETUP scene operation finds no source (`RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE`) and the capture dies. The capture of the live Recorder started as soon as its initial alignment existed (4.8 s here), so any run with this worker flow fails the same way.

Options considered:

- A. Change the worker so it pauses before the Recorder starts. Teacher-side flow change, not needed for the offline path.
- B. Let the world audit accept paused records. Relaxes a source rule.
- C. The offline episode window begins after the pause. The pause is a worker action before the Teacher starts; the data before it is not part of the episode.

Recommended option taken (CP-3394, CP-3440 A): C, as a production rule of the processor.

Rule (`act/offline/scan.py`, `replay.py`, `processor.py`):

- The boundary is determined from the recorded world `paused` flags: the last `paused=True` world record of the Teacher's reset epoch whose sim time is at or before the verified reset (`reset_complete.simulation_time_s`); the window starts at the first UNPAUSED world record after it. The pilot bag has five paused records before the Teacher (3.178 to 3.28 s at the worker's reset and 21.730 s); the window starts at step 9280, 21.742 s.
- Sources recorded before that record's bag receipt are not delivered to the Recorder engine. The Teacher's events, the planning-scene reads and `/clock` are always delivered.
- A paused world record inside the window (after the boundary, up to the end) stays INVALID: the scan names it (`OFFLINE_PAUSED_WORLD_IN_WINDOW`) and the engine refuses it as before.
- A bag without a pause before the reset keeps the whole bag as its window.

QC order: the Recorder's verified reset is its own first retained world record (21.742 s), the capture start is its first seed after the initial alignment (21.906 s), the Teacher's `reset_complete` event (sim 27.652 s) and first command (27.662 s) follow, so `verified_reset <= capture_start <= initial_capture <= Teacher start <= first command` holds. The verified reset is not later than the Teacher's own payload (24.574 s, the first record of its ring). The processor report carries `window_start` (record, sim time, bag stamp, last paused time, pauses before).

Contract impact: none. No source rule is relaxed. The processor decides where the episode begins instead of beginning at the first possible instant.

Tests (`test_p2_offline_processor.py`): the window start at the first unpaused record after the last pause; no pause gives the whole bag; a paused record inside the window is INVALID; the replay withholds sources recorded before the window but never events, scene reads or the clock.

Rollback: restore `scan.py`, `replay.py`, `processor.py` from `writer-artifacts/p2-roundA-base.tar.gz`.

Ledger CP: CP-3440.
