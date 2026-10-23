# Planning-scene freshness by bracketing

Date: 2026-10-08

Trigger: pilot bag `031b82c6`, row at 50.506 s. After the Teacher's `acm_apply` (49.854 s) the scene service stalled: one read took 251 ms of wall time, leaving a 148 ms hole in the Recorder's 20 Hz reads (sim 50.384 to 50.532 s). The row needs a read whose response is within 100 ms before it; none existed and the capture died with `INPUT_STALE` (cause `planning_scene`). The scene did not change: the reads on both sides of the hole carry the same geometry. Of 2261 reads, one hole exceeds 100 ms, none failed, the median read took 1.3 ms.

Options considered:

- A. Keep the age rule and avoid the stall (polling concurrency does not help: the service itself was blocked).
- B. Raise the 100 ms bound. Weakens the rule for every source.
- C. Extend the validity of a read to the stamp of the next read, only when the two reads are proven identical and no Teacher apply lies between them.

Recommended option taken (CP-3394, CP-3440 B): C.

Rule:

- A read at or before the instant `t` is valid at `t` if (1) the existing age rule `source_age_ok_ns` holds (unchanged), or (2) the first read after `t` carries IDENTICAL scene content (the normalized geometry the association compares: world objects, attached objects, colors; both equal to the governing association's receipt geometry), both reads are causally after the same governing association's apply, and no Teacher `/apply_planning_scene` call overlaps the interval from the earlier read's request to the later read's response (monotonic clock). If the content differs or an apply lies in the hole, only (1) applies.
- Where it plugs in: `synchronizer.bracketed_age_ok_ns(at_ns, stamp_ns, next_stamp_ns)` (`stamp <= at < next stamp`), next to `source_age_ok_ns` (the round-11 single age rule, which is not touched). The Recorder's source (`_planning_source_at` / `_planning_next_source_at` / `_bracket_at`) establishes the proof; the live physical audit (`_parts`) re-verifies the later read (components, causality, geometry) and applies the interval test instead of the age test for that one stamp; the recorder's row audit (`_audit`) admits the older planning stamp only with the bracket; the QC reader (`episode_physical_readback`) recomputes it from the two original reads.
- Evidence in the row: `planning_scene.bracket = {next_query_id, next_record}` exists only for bracketed rows. The row's `physical_stamps.planning_scene` stays the earlier read's own stamp; nothing is promoted to the instant.
- The other sources (physics, controller, cameras) keep the age rule.

Contract impact: a row may now rest on a planning-scene read older than 100 ms when the scene is proven unchanged; the row audit schema gains the optional `bracket` member. Rows without it are checked exactly as before. The QC reader additionally rejects a bracket whose later read is not after the instant, differs in geometry, does not follow the same association, or does not carry its own query id.

Tests (`test_p2_scene_bracket.py`): a 148 ms hole with an identical bracket is ready and the row carries the evidence; no following read, or one not after the instant, is not ready; a following read with different geometry is refused; at the source, a proven hole returns the two reads, a fresh read needs no bracket, a hole containing an apply is not bracketed, an apply long before it does not prevent it, and differing content keeps the 100 ms rule; the row audit admits the older stamp only with a well-formed bracket whose next read is after the instant; the QC reader recomputes it. The QC reader test cannot make the read 148 ms old (its fixture row sits at 2 ms), so the age arithmetic is covered by the provider and row-audit tests.

Rollback: restore `synchronizer.py`, `live_physical_audit.py`, `recorder.py`, `episode_physical_readback.py` and `episode_recorder_sources.py` from `writer-artifacts/p2-roundA-base.tar.gz`.

Ledger CP: CP-3440.
