# The apply-bounded scene bracket

Date: 2026-10-08

Trigger: pilot bag 429dbf50 (CP-3449). The Teacher's attach apply answered at 62.894 s, the grid row sat at 62.900 s, and the first planning-scene read that could follow the apply (it must begin after the apply's response) answered at 62.918 s. The row had no scene source and the capture died with `INPUT_STALE` (probe: `planning_scene` unready at 62.9 s), although the scene was the one the apply had just produced. Any geometry operation (attach, detach, sync) less than about 60 ms before a grid instant does this; the earlier bags passed by luck.

## Rule

For a row with no usable read at or before it, between the response of the Teacher's successful geometry apply that anchors the governing association and the first read after it, the scene source is that APPLY, when all of these hold:

1. the apply succeeded (`error` empty, `response.success` true) and it is the association's own apply record;
2. the first read after the row (causal after the same apply: it begins after the apply's response, in monotonic and simulation time) carries the association's geometry;
3. no other `/apply_planning_scene` call (successful or failed) lies between the apply's response and that read.

The row carries the apply as `planning_scene.record` (`query_id` is its call id) and the read as `bracket.next_record`; `physical_stamps.planning_scene` is the apply's response time; the instant must satisfy `stamp <= row < next read` (`bracketed_age_ok_ns`, unchanged). An apply without the following read is never a source. Every other scene rule is unchanged: the 100 ms age rule, the read bracket of CP-3440 B (a row that has a read at or before it keeps those rules), the association rules, the geometry comparison including colours.

## Where

- `RosRecorderSources._apply_bracket_at` (the proof for rows), used by `_planning_source_at` and `_planning_next_source_at` after the read bracket.
- `LivePhysicalAuditProvider._parts` / `_verify_apply_anchor`: an apply source requires the following read, which is verified against the same association (`LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID` for other content, `LIVE_PHYSICAL_SCENE_INVALID` for a failed or foreign apply).
- `EpisodeRecorder._audit`: an apply record is admitted only with its bracket (`EPISODE_SOURCE_STALE` otherwise).
- `verify_episode_physical_rows` (the QC reader): recomputes the same facts from the original records (the apply equals the association's anchor and succeeded, the bracket's read is causal after it with the association's geometry, the instant lies between the two, no association changes the scene inside). `EPISODE_PHYSICAL_READBACK_INVALID` otherwise.

## Tests (`test_p2_apply_bracket.py`, 13)

The numbers of the real case relative to the apply: row +6 ms, following read +24 ms. Apply then a matching read: ready, the row carries both. Following read with other content: invalid. Failed apply, foreign apply: invalid. No following read: not ready. A second apply between (successful or failed): no source. A read at or before the row: the read rules decide. Row audit: an apply without its bracket is refused. QC reader: the valid case passes; changed geometry, failed apply, not the anchor, no bracket, read before the apply, read not after the instant are refused. RED run first: 7 of 12 failed before the change.

## Contract impact

A row's scene evidence may now be an apply plus the read that follows it instead of a read. The recomputed facts are the same kind as the existing bracket (identical content, nothing applied between), with the Teacher's successful apply as the lower bound.

Rollback: `writer-artifacts/p2d-applybracket-base.tar.gz` (the four source files and the bracket test as they were), sha256 beside it.

Ledger CP: CP-3449.
