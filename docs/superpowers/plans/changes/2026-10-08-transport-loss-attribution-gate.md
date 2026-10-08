# The per-topic transport-loss attribution gate (phase C)

Date: 2026-10-08

Trigger: the amendment (section 6) left a gate open when it reversed the CP-3457 interim decision: before any formal collection, every topic an episode depends on needs a loss-detection rule or a recorded argument that a loss there cannot make a VALID episode wrong, and the transport losses `ros2 bag record` reports (6 on 147cb073, 7 on the L2 bag 45315499) must be attributed to a topic and judged. The coordinator chose the policy under CP-3394: a detected loss inside the window on a topic the episode uses is INVALID (`OFFLINE_TOPIC_LOSS:<topic>`); outside the window or on an unused topic it is recorded; an aggregate that cannot be attributed fails closed.

Options considered for the aggregate:

1. Treat any reported loss as INVALID (CP-3457). Rejected before: it needs no attribution but cannot say what was lost.
2. Per-topic counters from the recorder. Not available at the default log level (see C1); **available with `--log-level debug`, added in C5 below.**
3. Judge every used topic on its own continuity, then reconcile the recorder's total with what the topics show missing; fail closed on the shortfall. Taken.

## C1. Attribution: what the recorder can and cannot say

`ros2 bag record` (Jazzy) prints one line at stop: `Number of messages lost on the transport layer: N`. There are no per-topic counters in that output, in `metadata.yaml`, or in the QoS events the recorder keeps (`bag-qos.yaml` holds the requested profiles only). The total cannot be attributed from the recorder's output. The next-best evidence is the bag itself, per topic, from the topics' own ordering keys (`phasec/c1-survey.py`; full tables in `phasec/c1-147cb073.json` and `c1-45315499.json`).

What the topics show, over the whole bag (messages missing = grid or sequence gaps; a gap that also appears on `/clock` is a producer stall, not a lost message):

| Topic | 147cb073 | 45315499 |
| --- | --- | --- |
| `/clock` | one 18 ms gap at 11.8 s (the producer skipped 8 cycles; `/clock`, the three controller states and `/joint_states` all show it) | none |
| `arm` / `gripper` / `neck` `controller_state` | 2 / 3 / 4 missing around 9.0 s and 13-22 s, all before the verified reset (22.8 s) | 2 / 1 / 1 missing, 7.2 s and 11.6 s, before the verified reset (12.6 s) |
| `/joint_states` | the same producer stall only | none |
| `color` images | one image lost at 21.6 s per camera while `camera_info` arrived (before the reset) | none |
| `camera_info`, chunks, world (publisher sequence), `robot_contacts` (step sequence), planning-scene reads (bag count = sidecar count), Teacher events (`seq`) | complete | complete |
| `scene_state` | a world record without its pair: none | none |
| Total that can be placed | 11 | 4 |
| Recorder's total | 6 | 7 |

Every gap found on either bag lies before the verified reset, so none is inside an episode. For 147cb073 the placeable total (11) covers the recorder's 6. For 45315499 it does not: **7 reported, 4 placeable, 3 not on any topic the scan can judge.** Candidates for the three: the leading or trailing messages of a topic (a loss at the edge of a stream leaves no gap), and topics with no continuity evidence (`/so101/simulation/joints`, two latched messages; the empty hazard latch). None of them is a topic an episode's rows depend on, and every topic they depend on is complete over the window. That is an argument, not a proof, and the gate does not accept it: the recorder's total is a hard fact and the shortfall fails closed.

## What changed

- `act/offline/scan.py`: the scan decodes `/clock`, `/joint_states`, `scene_state` and the colour images too, and judges them (below); `_topic_loss` returns the per-topic facts and the reconciliation. The recorder's total is read by `processor.load_loss_facts`: the `transport_lost` key of `record-stats.json`, or, for stats written before the key existed (147cb073), the line in `bag-record.log` beside them; unknown fails closed (`OFFLINE_TRANSPORT_LOSS_UNKNOWN`).
- New rules (window: from the start of the retained world, or the verified reset, to the terminal + 0.1 s; images over the rows interval, verified reset to normal stop):
  - `/clock`: 2 ms stamp grid.
  - `/joint_states`: 10 ms header-stamp grid (observed exact on 19,700 messages of both bags; the first message after a stall is the only exception, and a stall is also a `/clock` gap).
  - `scene_state`: published in the same call as the world record (`SimulationEvidencePlugin::update`), so every world record of the window has a scene state with the same step and stamp.
  - colour images: every `camera_info` stamp of the rows interval has its image.
  - planning-scene reads: the bag's count equals the sidecar's own count (`record-stats.json`).
- Unused topics are counted and recorded only: `robot_contacts` (a lost sample is a lost sample of a chunk, covered by the chunk rules), `neck` `controller_state`, `joints`, `physics_hazard`.
- New `act/topic_loss.py` and a `topic-loss.json` document beside the episode (kind `ACT_TOPIC_LOSS_GATE`, rule `topic_loss_v1`): per topic the rule, message count, gaps, stalls, missing inside and outside the window; the window; the reconciliation (`reported`, `attributed`, `unattributed`); the verdict. The processor writes it for every bag with a timeline, valid or not.
- QC: `QC_RULE_VERSION` is `act_data_qc_v4`; a report has a third check, `topic_loss_gate` (status, reason, the document's sha256, rule version, losses in window). `recompute_native_qc` reads the document beside the episode (or `--topic-loss`), refuses an absent, malformed, old-rule or foreign-identity one (`NATIVE_QC_TOPIC_LOSS_*`) and fails the report on a failed gate. The QC memo fingerprint covers the document and the code digest covers `topic_loss.py`. Reports and memos of rule v3 are refused, as intended.
- Test fixtures: `offline_synthetic_bag.py` now carries a joint state every 10 ms, a scene state per world record, `transport_lost` and the reads count in its stats; `test_act_qc_report_publication.py` builds the v4 report.

Where the rule runs, and what the QC check is. A sealed episode holds the retained rows and audit streams, not these raw topics, so the QC cannot recompute the scan. The check is an authenticated record: the QC binds the document by digest, requires a PASS gate, and the rule version change makes older evidence unusable. The detection itself is only possible where the bag is (the scan). The coordinator's wording "QC rules" is met in that sense; the alternative (putting the raw topics into the audit) would have meant a new audit stream and a schema change.

## Policy as implemented

- Loss inside the window on a used topic: `OFFLINE_TOPIC_LOSS:<topic> ...` (the older rules keep `OFFLINE_SOURCE_GAP` and `OFFLINE_CAMERA_GRID`).
- Loss outside the window, a stall, or a loss on an unused topic: recorded in `topic-loss.json`, never fatal.
- Aggregate: `unattributed = reported - (all messages missing on any topic, stalls excluded)`; above zero fails closed. The placeable total counts losses outside the window too, but never the `/clock` gap itself (it defines the stall and explains no lost message).

## Results on the eight golden inputs

| Input | Before | After | New reasons |
| --- | --- | --- | --- |
| 147cb073 | VALID, QC PASS | VALID, QC PASS | none |
| **45315499 (L2)** | VALID, QC PASS | **INVALID** | `OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 3 of 7` |
| 429dbf50 | INVALID | INVALID | none |
| 8d9ed9d3 | INVALID | INVALID | `OFFLINE_TOPIC_LOSS:/clock` (547 gaps), `OFFLINE_TOPIC_LOSS:/joint_states` (4 gaps) |
| 031b82c6 | INVALID | INVALID | `OFFLINE_TOPIC_LOSS:/clock` (1 gap) |
| fault source_gap, queue_overflow | INVALID | INVALID | none |
| fault late | INVALID | INVALID | `OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads` (the fault bag drops reads) |

**Finding, reported before anything else was changed: under the coordinator's policy the L2 bag becomes INVALID.** Nothing was loosened to avoid it. The cause is only the aggregate clause; every per-topic rule passes on both reference bags (nothing missing inside the window). The L2 episode therefore cannot be re-processed to a sealed VALID episode under the new rules; the QC and readback evidence of the L2 run remains a record of rule v3.

147cb073 compared with its golden: the processor outputs are EQUIVALENT under the nondeterminism list plus the phase C items (N10: `topic-loss.json`, the `topic_loss_gate` check, the rule version, the report facts). Its `qc-report.json` differs from the v3 report in exactly the rule version, the added `topic_loss_gate` check (PASS, 0 lost in window, document sha256 `2fb7d2e1...` for run C2) and the two digests that follow from the changed episode bytes (N3).

## Tests (RED first)

`test_c_topic_loss_gate.py`, 22 tests (RED against c039b78be: the module does not exist). Synthetic bags with: a joint state lost inside the window, a scene-state transition lost, a clock message lost, an image lost while its camera info arrived, fewer planning-scene reads than the sidecar made, a loss outside the window (recorded, not fatal, attributed), an unaccounted transport loss (fails closed, also partly accounted: `2 of 3`), an unknown total, a producer stall (not a loss); the processor verdict and the document for an INVALID and a VALID bag; the loss facts from stats and from the recorder's log; the QC check (clean, absent, garbage, foreign attempt, old rule, non-canonical, failed document); the v4 report shape (a v3 report, a missing check and a failed gate under a PASS verdict are refused); the memo fingerprint covers the document.

## Open points

1. The decision on the L2 bag (accept the three as edge losses with a recorded argument, or keep it INVALID and re-record). Not mine to take.
2. "Placeable" is a count, not an assignment: where a topic's own gap is larger than the share of the total that belongs to it, the gate still passes. It can never pass a shortfall; it can pass an excess.
3. The leading and trailing messages of each stream are not judged (no gap is visible there).
4. When the gate fails before the replay (a preset reason), the engine still tries a FAILED seal, which fails on the L2 data with `AUDIT_WINDOW_INVALID`: the retained record is unsealed. Unchanged behaviour for every preset reason; noted because L2 now takes this path. **Fixed by CP-3394** (`2026-10-09-first-live-findings-seal-readback-evidence`, P1(b)): scan-level reasons no longer stop the replay from delivering the Teacher events, so the record is sealed `FAILED` without the second reason.

## Rollback

`p5c-base.tar.gz` (sha256 in `p5c-base.tar.gz.sha256`) holds the files this change touched as of c039b78be.


## C5. Per-topic loss reporting from the recorder (CP-3394)

Decision (coordinator): implement per-topic reporting for new bags and keep the aggregate rule for bags already recorded; L2 45315499 stays INVALID, and the rule that would have excused its three unplaced losses was rejected.

Investigation of the L2 residual (before the decision): the aggregate is the sum of `message_lost` callbacks per subscription, over the 16 topics the recorder subscribes to plus the events and planning-scene reads topics only (not /rosout, /tf or /events/*). A late join (a transient-local history overflow before the recorder subscribes) is not counted: a throwaway publisher with depth 10 sent 100 messages before the recorder joined, the bag held 10 and no loss was logged. Every recorded topic of L2 is gapless over its own span except the controller states (4 placed gaps); the staggered starts of the three controller states (5, 7 and 8 ticks after `/clock`) are late join, reconcile exactly with `/clock` and are not losses. The three unplaced losses are therefore on a topic or at an edge the bag cannot show, and only a per-topic figure can say which.

What changed:

- `raw_recorder.py`: `ros2 bag record` runs with `--log-level debug` (`RECORDER_LOG_LEVEL`); `transport_lost_by_topic_from_log` takes the last cumulative total per topic from the DEBUG lines; `stop()` writes `transport_lost_by_topic` into the stats next to `transport_lost`. A flooded two-topic test publisher gave 54 + 56 = 110 = the aggregate.
- `processor.load_loss_facts` returns `transport_lost_by_topic` (None when the key is absent or malformed: old bags). `scan_bag(..., transport_lost_by_topic=)` runs `_with_breakdown` when it is a dict.
- Gate logic with a breakdown: the per-topic sum must equal the aggregate and every name must be a recorded topic (else `OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED`); a used topic's reported count must be at most what its rule shows missing anywhere in the bag (messages missing on the grid or sequence, stalls included, images without their `camera_info`, reads short of the sidecar), else `OFFLINE_TOPIC_LOSS:<topic> reported=n detected=m`; unused topics (`neck` controller state, contacts, joints, physics hazard) are recorded only. `topic-loss.json` gains `transport_lost.by_topic` and per-topic `reported` / `detected` fields only when a breakdown exists, so documents of old bags are byte-identical to before; the rule version stays `topic_loss_v1`.
- Span checks: the publisher-sequence (world), chunk sequence, Teacher event `seq` and planning-scene-read rules existed; the robot-contact step span is new and is decoded only when the recorder reports a loss on that topic (the topic is unused by the episode, and decoding 46k messages on every scan is not worth it). The Teacher's terminal event carries no published count (payload: status, execution status, task result, failure), so the events tail cannot be checked against one: a loss reported on the events topic after a gap-free `seq` that reaches the terminal event is a message after it and is recorded only.
- Cost of debug logging, measured on a synthetic 6-topic, 500 Hz (3 kHz total) reliable publisher over 20 s, two alternating repeats: recorder CPU (utime + stime) 115 and 142 ticks at `info`, 122 and 172 at `debug` (the repeat-to-repeat spread is as large as the difference, so no overhead is resolved; at most about 20% of a recorder that uses about 6% of a core); recorded counts varied between repeats at both levels (51.9k to 58.8k of 60k, from discovery timing) and not with the level; no loss was reported at either level. The log grows from 2 KB to 8-9 MB (rcl logs two lines per received message; `ros2 bag record` has no per-logger switch, `--ros-args` is refused). A 90 s production recording is about 40 MB of log. Not measured on the live stack (not allowed in this round).

Tests (RED against CP-3471): 13 new/changed in `test_c_topic_loss_gate.py` (breakdown with no loss, outside-window loss explained, the L2 shape reported-without-gap INVALID and naming the topic, unused topic recorded only, sum mismatch both ways, unknown topic, in-window gap stays INVALID, events tail, planning-scene reads, contact span read lazily, old bag keeps the aggregate rule, the log parser, the processor end to end) and `test_rec13_raw_recorder.py` (the real recorder reports `transport_lost_by_topic == {}` and a debug log). The eight golden inputs have no breakdown; their verdicts are unchanged (see the ledger note).
