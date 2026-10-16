# SO-101 ACT collection: phase-1 delivery fix and in-campaign retry of INVALID scenes

Status: PROPOSED on 2026-10-16, awaiting human confirmation. This amends the two-phase collection design (2026-10-15).

## Why

The formal collection EXP-615 committed 56 of 70 scenes. All 70 Teacher runs passed. The 14 INVALID scenes were rejected by the offline processor because of recording-time delivery timing:

| Reason | Scenes |
| --- | --- |
| `NO_NEW_ACQUISITION` | 7 |
| `RECORDER_SOURCE_ALIGNMENT_SOURCE_OUTSIDE_TIMING_WINDOW` with `INPUT_STALE` | 5 |
| `INPUT_TIMESTAMP_FUTURE` | 1 |
| `OFFLINE_TOPIC_LOSS` (`/joint_states`, `scene_state`) | 1 |

EXP-614 had 4 of 40 for the same reasons. The phase-2 replay runs on the recorded receipt clock, so reprocessing gives the same verdict.

Human decisions (2026-10-16):
1. "先修好阶段一的投递时序问题。" Fix the phase-1 delivery timing first.
2. "代码改成支持重跑失败case（类似retry failures）。" Support re-running failed cases.
3. "清理历史证据" (done: `R/evidence-deletion-20261016b`).
4. "重跑70" Re-run the 70 formal scenes.

## Diagnosis (evidence: `REG/diag-delivery-20261016/`)

All 110 bags of EXP-614 and EXP-615 were joined with the camera publish trace and the probe subscriber trace. There are three classes of late camera delivery:

| Class | Events / 110 episodes | Shape | Seen late by |
| --- | --- | --- | --- |
| A | 24 | One image 110 to 130 ms late, delivered together with its successor; `camera_info` held up to about 1.5 s, then a burst | recorder and probe |
| B | 26 | All topics, `/clock` included, 300 to 335 ms late, then a burst | recorder only |
| C | about 15 | Multi-frame holds of 0.4 to 2 s | recorder and probe |

Transport facts:
- `rmw_fastrtps_cpp` 8.4.4 with Fast DDS 2.14.6, and no XML profile.
- Camera publishers are reliable, keep_last 16.
- Images are 921 KB.
- Containers run with `--network none --ipc private`.

Class A is the reliable-DDS repair path:
- A reader that misses a sample holds every later sample until the writer repairs it.
- For images, the next image's heartbeat triggers the repair, so the hold is about one frame.
- `camera_info` waits for the periodic heartbeat.

This was reproduced in throwaway containers from the shard image: eight mini-shards, the real `ros2 bag record`, synthetic 920 KB images, and CPU load. The baseline had 176 late messages in 31,300. With a Fast DDS profile setting a 20 ms writer heartbeat period and a 1 ms NACK response delay, two runs had zero late messages above 50 ms. A larger SHM segment did not help.

Classes B and C are not explained yet. Class B is a stall of the recorder process alone. The `frm-047` loss fits the same stall outrunning the depth-10 history of a 500 Hz writer.

## Part 1 — Delivery fix

1. **Fast DDS profile.**
   - Add `src/so101_demo_py/config/dds/fastdds-collection.xml`. It is a default publisher profile that sets only `<times>`: `heartbeatPeriod` 20 ms and `nackResponseDelay` 1 ms. The draft is `REG/diag-delivery-20261016/scripts/hb.xml`.
   - Install the file with the package.
   - Set `FASTRTPS_DEFAULT_PROFILES_FILE` to its installed path in the instance environment of every collection ROS process: shard, Teacher and processor (`runtime/act_instance/identity.py` `instance_environment`, or the container `--env` list in `runtime/container_campaign/launch.py`).
   - Leave `RMW_FASTRTPS_USE_QOS_FROM_XML` unset, so the ROS QoS in code stays authoritative.
   - The file is part of the shard image and of the source sha, so the controlled identity changes and a new qualification is required.
2. **Recorder-stall diagnostic (class B, no behaviour change).**
   - In phase 1, compare probe receipt with recorder receipt per topic.
   - Log `RECORDER_ONLY_STALL` with the gap, the topic count and the recorder process thread state, from the existing thread sampler, whenever the recorder lags the probe by more than 100 ms.
   - The aim is to identify class B in the next run. Its fix is a later decision.
3. **Unchanged.**
   - Every data rule and threshold: the 100 ms windows, `max_source_age_s`, loss, continuity, QC.
   - The publisher QoS in code, and the 500 Hz writer history depth. Raising that depth needs `mujoco_ros2_control` changes and is deferred until class B is understood.

## Part 2 — Retry INVALID scenes inside the campaign

**Behaviour.**
- A new optional campaign-config key `retry_invalid_max_rounds` takes an integer from 0 to 3. It is absent by default, which means 0 and today's behaviour byte for byte. It is not part of the controlled identity.
- After phase 2, a scene is a retry candidate when its latest attempt is PROCESSED with a Teacher PASS and an INVALID data verdict.
- Candidates are recorded again in a new phase-1 round on the same eight shard slots, made durable with one syncfs, and processed in phase 2.
- This repeats up to the configured number of rounds, while candidates remain and the round fits the deadline.
- Never retried: Teacher FAIL, FINAL_AT_PHASE1, FAULT and MISSING scenes.
- The latest attempt with a final verdict decides each scene, and every attempt stays listed.
- Retry is formal-plane only. The campaign owner refuses it on the qualification plane, and admission refuses it as well. Qualification therefore still measures first-attempt quality, and the existing qualification reports still recompute byte for byte.

**Naming.**
- Round-0 numbering continues into the retry rounds:
  - waves continue the global index (`wave-N`, generation N+1);
  - the phase-1 attempt stays `<scene>-lease-1`, which is unique per wave;
  - the processing attempt number continues across rounds (`<scene>-lease-1-proc-<n>`).
- No shard or processor container code changes for retry.
- Per-round Host files:
  - Round 0 keeps today's names.
  - Round r of 1 or more writes `host/retry-<r>/phase1-durability.json`, `processing-journal.jsonl` and `processing-result.json`.
  - The round's decision goes in `host/retry-round-<r>.json`, with candidates, plans, the time estimate and RUN or SKIPPED with its reason.

**Time.**
- A round runs only if it fits the deadline: recording (the largest observed round-0 wave time times the retry waves), plus sync, plus processing (the largest observed task time times ceil(k / processors)), all within total − `verification_reserve_s`.
- Otherwise it is skipped with `RETRY_ROUND_DOES_NOT_FIT_DEADLINE`.
- A disk check skips with `RETRY_ROUND_DISK`.
- The phase-1 dispatch fence is reopened only for a round, and only when the previous stop was the phase-1 deadline.
- An infrastructure error in a retry wave ends retrying (ABORTED). The combined result is still written from the earlier rounds, and the CLI exits non-zero.

**Results.**
- With no rounds, `host/campaign-result.json` and `collection-index.json` stay byte-identical.
- With rounds:
  - the index is schema 3;
  - `collected_tasks` lists every recording attempt, with `recording_round`, `wave_index` and `final`;
  - `committed_episodes` holds only the final attempt per scene, so the export (`act/bundle.py`) needs no change.
- The campaign result carries `rounds` and `recording_attempts` per scene.

**Code** (touch-point map in the implementation plan):
- `inference/config.py`
- `container_campaign/processing_limits.py`
- `act/parallel_collection.py` (`plan_campaign_waves` gains `first_wave_index` and `recording_round`)
- `container_campaign/owner.py` (round loop, per-round files, reopen)
- `container_campaign/coordinator.py` (`reopen_dispatch`)
- `container_campaign/processing_scheduler.py` (admit slots once, keep generations, journal per round, continue proc numbers)
- `container_campaign/processing_verifier.py` (`verify_processing(host_dir=…)`, new `verify_rounds`)
- `container_campaign/result_verifier.py` (schema-3 index)
- `cli/act_collect_parallel.py` (summary)
- `unified/admission.py` (refuse retry on the qualification plane)
- Templates: `--retry-invalid-max-rounds`; w8f only.

## Verification sequence

1. Unit tests for each piece, including byte-identical round-0 output and the recompute of a stored two-phase qualification run, then the Host gate.
2. Rebuild both images.
3. EXP-616, a 16-scene debug run at cap 8 (retry off). Compare the class A to C counts per episode with EXP-614 and EXP-615 using the diagnosis scripts. Expect class A and the `camera_info` holds to be near zero. Class B is measured by the new diagnostic.
4. EXP-617, the 40-scene qualification at cap 8 (retry off by rule).
5. EXP-618, the formal 70 with `retry_invalid_max_rounds` 2 and a 9000 s total.
   - Expected first-round VALID is about 63 or more of 70, from class A removed. The retry rounds should recover most of the rest.
   - Projected time: 92 min plus about 15 to 20 min per round for about 7 scenes. The template projection warns if the total is short.

## Open questions with recommendations

| Question | Recommendation |
| --- | --- |
| Retry every INVALID with Teacher PASS, or only an allowlist of delivery reasons? | Every one. An allowlist can come later if a deterministic INVALID wastes rounds. |
| Default rounds for the formal run? | 2. |
| Class B? | Diagnose in EXP-616 with the new log; fix in a later change. |
