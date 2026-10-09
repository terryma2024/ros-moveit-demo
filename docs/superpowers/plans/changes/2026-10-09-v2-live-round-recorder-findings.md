# First live round of Teacher policy v2: the data-side findings and their fixes (CP-3489)

Freeze p7-claude-1009c, runs T01-T14 (T15-T20 and the faults did not run: the prestart check refused the edited worktree). The Teacher
passed 13 of 14 runs and the v2 place height was measured in every one of them. 5 of 14 were VALID. None of the nine data failures is
caused by v2: each is on the Recorder/QC side or on the host, and each was reproduced by replaying the retained bag through the
production processor.

| Run(s) | Reason | Cause | Fix |
| --- | --- | --- | --- |
| T03, T04, T10 | `LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID` (`live_physical_audit.py:71`) | The 20 Hz scene read ran concurrently with a geometry-changing Teacher apply (attach, sync): the apply takes effect about 8 ms into its 20 ms window, so a read starting in the next 1-12 ms already shows the new scene while the governing association is still the old one. Present in the v1 runs too (their straddling reads happened to show the old scene). | Item 1 |
| T03, T06 | `OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads missing=N` | The first 5 (T03) and 3 (T06) sidecar reads, at sim time 0, were published before `ros2 bag record` had matched its subscription. They are in the sidecar and not in the bag, and the rule counted them as losses inside the window. | Items 2 and 3 |
| T01, T09 | `INPUT_STALE` | The scene-read sidecar thread stalled (T01: 336, 360 and 338 ms; T09: up to 958 ms): the periodic `os.fsync` of its file ran in the read loop on a busy filesystem. The row at the stalled grid instant had no planning read within the age rule or its bracket. The bags really lack the reads, so these stay INVALID. | Item 3 (new bags) |
| T08, T13, T14 | `ENDPOINT_INITIAL_CAPTURE_INVALID` -> `AUDIT_WINDOW_INVALID` (`native_endpoints.py:305`) | The initial capture waited until every world source received so far had its native chunk. A world source on the first step of the next chunk (evidence steps 1 mod 5 against chunks 50n+1) is received before that chunk is published, so the capture landed a whole chunk (100 ms) later: 158 ms after the first eligible source, over the 100 ms rule. 3 of 14 runs, a property of the phase between the evidence grid and the chunk boundary. | Item 5 |
| T06 | `DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE` (`dynamic_mujoco_execution.py`) | A Teacher failure with no proven cause (the bag has every evidence and scene-state step after the stop, with the same latency as the passing runs; the Teacher's own observers did not select one within 0.5 s). The data reasons that follow are consequences. | Item 4 (diagnostics only; no behaviour change) |

## Decisions and what was changed

1. **Scene read concurrent with an apply.** When a read's interval overlaps the apply of an association other than the governing one,
   the read's geometry is accepted if it equals EXACTLY the geometry of the governing association or of that overlapping association
   (`scene_association.concurrent_apply_geometry_matches`). Anything else still fails. The same rule applies in the sealed readback
   (`episode_physical_readback.py`, `causal_read`). In the offline replay the Teacher event of an apply arrives after the read, so a
   mismatch waits 50 ms of replay time for it before it counts as a failure (`OfflineRosSources.APPLY_SETTLE_NS`).
2. **Reads before the window.** `scene reads missing` counts only reads whose simulation time is inside the reported window
   [`window.begin_sim_ns`, `window.end_sim_ns`], on both the sidecar and the bag side; earlier reads are recorded as
   `missing_outside_window`. The window start was chosen over the bag-ready anchor because it is already the gate's own window, needs no
   clock mapping, and no row uses a read older than the first row. A bag whose sidecar file is absent or inconsistent keeps the old
   whole-bag count rule.
3. **Sidecar.** The `fsync` is on its own thread, so the read loop never waits for it; publication on the topic starts only once the bag
   node is among the topic's subscribers (the reads before are still written to the sidecar file). `record-stats.json` carries
   `scene_reads.published`.
4. **Diagnostics.** On `DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE` the message keeps its code and appends the facts, which are also
   in the manifest as `post_stop_source_unavailable`: iterations, the pending candidate's step and sequence, the scene-frame steps held,
   the last scene error, how often the loop waited for a scene frame, how many candidates were skipped as generated before the stop.
   The retry behaviour stays unchanged until the cause is known (decision 5: not now).
5. **Initial capture on the covered prefix.** `_capture_native_initial_step` selects among the world sources whose native step is
   retained and no longer waits for newer ones. A source inside the raw window without its step is still `ENDPOINT_NATIVE_SOURCE_INVALID`,
   and the expiry rule still applies to the sources that are waited for.
6. **Evidence cadence (CP-3488, option a).** `SimulationEvidencePlugin::update()` gates on an integer-nanosecond grid:
   `period_ns = llround(1e9 / rate)`, `step_ns = llround(timestep * 1e9)`; initialisation refuses a rate whose period is not a multiple
   of the step; a message is published when `floor(time_ns / period_ns)` changes. The accumulated double time had made the old gate
   publish every 5 steps in the 8-16 s and 32-64 s binades and every 6 steps (12 ms, 83 Hz) in 4-8, 16-32 and 64-128 s.

## Offline re-run of the live roots (processor of this change)

T02, T03, T04, T05, T07, T08, T10, T11, T12, T13, T14: VALID with QC PASS. T01 and T09: INVALID (`INPUT_STALE`, the bags lack the reads).
T06: INVALID (the Teacher failure; the topic-loss reason is gone).
